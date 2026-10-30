"""Jobs - tache de labellisation par operateur.

Un job represente une tache de labellisation assignee a un operateur sur un document.
Chaque document passe par deux etapes : validation puis consensus.

GET   : liste des jobs, detail avec champs structures par page/section
POST  : creation d'un job, proposition de valeur, soumission
PATCH : finalisation (submit)
"""

from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.functions import count

from adam_api.dependencies.auth import Caller, UserCaller, get_caller
from adam_api.dependencies.db import get_db
from adam_api.services.consensus import try_resolve
from adam_core.enums.status import (
    DocumentFieldStatus,
    DocumentStatus,
    FieldValueType,
    JobState,
    JobStep,
)
from adam_core.models import Dataset, Document, DocumentField, FieldProposal, Job, User
from adam_core.schemas.responses import (
    FieldProposalOut,
    JobCreatedOut,
    JobDetailOut,
    JobFieldItemOut,
    JobOut,
    JobPageOut,
    JobSectionOut,
    JobSubmitOut,
)
from adam_core.utils.exceptions import raise_conflict, raise_not_found, raise_unprocessable
from adam_core.utils.logging import get_logger

router = APIRouter(prefix="/jobs", tags=["Jobs"])

#: Reponse 403 des routes reservees a l'operateur du job (documentation OpenAPI).
_AGENT_ONLY: dict[int | str, dict[str, Any]] = {
    403: {"description": "Job reserve a son operateur"},
}

#: Statuts d'un document dont les champs ne sont pas encore crees.
_NOT_READY_STATUSES = (DocumentStatus.RECEIVED.value, DocumentStatus.INGESTED.value)
logger = get_logger(__name__)


class JobIn(BaseModel):
    dataset_id: int
    document_id: int
    agent_id: int  # TODO Sprint 3 : remplacer par caller.organisation_id


class FieldProposalIn(BaseModel):
    document_field_id: int
    value: Optional[str] = None
    value_type: Optional[str] = None
    reason: Optional[str] = None


class FieldProposalBulkIn(BaseModel):
    proposals: List[FieldProposalIn] = Field(min_length=1, max_length=1000)


# GET


@router.get("", response_model=List[JobOut])
async def list_jobs(
    agent_id: Optional[int] = None,
    dataset_id: Optional[int] = None,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> List[Job]:
    """Liste les jobs avec filtres optionnels."""
    query = select(Job)
    if agent_id:
        query = query.where(Job.agent_id == agent_id)
    if dataset_id:
        query = query.where(Job.dataset_id == dataset_id)
    if state:
        query = query.where(Job.state == state)
    return list((await db.execute(query)).scalars().all())


def _spec_place(spec: Any) -> tuple[int, str, Optional[str], Optional[str]]:
    """(page, section_id, section_label, field_key) d'un champ ; un champ sans spec va page 0."""
    if spec is None:
        return 0, "unknown", None, None
    return spec.page, spec.section_id, spec.section_label, spec.field_key


def _job_field_item(df: DocumentField, field_key: Optional[str], job: Job, proposal: Any) -> Any:
    """Le champ vu par l'operateur : sa proposition (None si elle n'existe pas)."""
    return JobFieldItemOut(
        id=df.id,
        field_key=field_key,
        step=job.step,
        value=getattr(proposal, "value", None),
        value_type=getattr(proposal, "value_type", None),
        reason=getattr(proposal, "reason", None),
    )


def _job_pages(job: Job, proposal_index: dict[int, FieldProposal]) -> List[JobPageOut]:
    """Champs du document structures par page puis section, avec la proposition du job."""
    sections: dict[tuple[int, str], JobSectionOut] = {}
    for df in job.document.document_fields:
        page_num, sec_id, label, field_key = _spec_place(df.field_spec)
        section = sections.setdefault(
            (page_num, sec_id), JobSectionOut(section_id=sec_id, section_label=label, fields=[])
        )
        section.fields.append(_job_field_item(df, field_key, job, proposal_index.get(df.id)))

    by_page: dict[int, List[JobSectionOut]] = {}
    for (page_num, _sec_id), section in sections.items():
        by_page.setdefault(page_num, []).append(section)
    return [JobPageOut(page=page, sections=by_page[page]) for page in sorted(by_page)]


@router.get("/{job_id}", responses=_AGENT_ONLY)
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    caller: Caller = Depends(get_caller),
) -> JobDetailOut:
    """Detail d'un job avec les champs du document structures par page puis section.

    Inclut la proposal de cet operateur sur chaque champ si elle existe.
    Point d'entree principal de l'IHM labellisation.

    Reserve a l'operateur du job : lire la proposition d'un autre avant la sienne fausse le
    consensus. Un Administrateur Metier qui doit trancher un champ en litige n'a pas besoin de
    ce detail, il ouvre son propre job et y propose sa reponse.
    """
    result = await db.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(
            selectinload(Job.document)
            .selectinload(Document.document_fields)
            .selectinload(DocumentField.field_spec),
            selectinload(Job.field_proposals),
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise_not_found(Job)
    _ensure_job_agent(job, caller)

    sorted_pages = _job_pages(job, {p.document_field_id: p for p in job.field_proposals})

    return JobDetailOut(
        id=job.id,
        step=job.step,
        state=job.state,
        agent_id=job.agent_id,
        document_id=job.document_id,
        dataset_id=job.dataset_id,
        started_at=job.started_at,
        submitted_at=job.submitted_at,
        pages=sorted_pages,
    )


# POST


def _job_created_out(job: Job) -> JobCreatedOut:
    return JobCreatedOut(
        id=job.id,
        step=job.step,
        state=job.state,
        agent_id=job.agent_id,
        document_id=job.document_id,
        dataset_id=job.dataset_id,
    )


@router.post("", response_model=JobCreatedOut, status_code=201)
async def create_job(
    payload: JobIn, response: Response, db: AsyncSession = Depends(get_db)
) -> JobCreatedOut:
    """Cree un job et l'assigne a un operateur.

    409 tant que le document est RECEIVED ou INGESTED : il n'est disponible qu'a partir de
    IN_PROGRESS, quand ses champs ont ete crees.

    Idempotent : un agent n'a qu'un job (non annule) par document. Si celui-ci existe deja, il
    est rendu tel quel avec un 200 au lieu d'un 201. La ligne du document est verrouillee le
    temps de la verification, sans quoi un double clic ou deux onglets, simultanes, creaient
    chacun leur job.
    """
    doc = await db.get(Document, payload.document_id, with_for_update=True)
    if not doc:
        raise_not_found(Document)
    if doc.status in _NOT_READY_STATUSES:
        # Les champs n'existent qu'une fois la pre-alimentation passee : RECEIVED (fichier recu)
        # et INGESTED (pages rendues) n'en ont pas, un job y serait vide.
        raise_conflict(Document, "en cours de preparation, pas encore disponible")

    agent = await db.get(User, payload.agent_id)
    if not agent:
        raise_not_found(User)

    existing = (
        await db.execute(
            select(Job)
            .where(Job.document_id == payload.document_id)
            .where(Job.agent_id == payload.agent_id)
            .where(Job.state != JobState.CANCELLED.value)
            .order_by(Job.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        response.status_code = 200
        return _job_created_out(existing)

    submitted_count = (
        await db.execute(
            select(count(Job.id))
            .where(Job.document_id == payload.document_id)
            .where(Job.state == JobState.SUBMITTED.value)
        )
    ).scalar_one()

    step = JobStep.VALIDATION.value if submitted_count == 0 else JobStep.CONSENSUS.value

    job = Job(
        dataset_id=payload.dataset_id,
        document_id=payload.document_id,
        agent_id=payload.agent_id,
        step=step,
        state=JobState.ASSIGNED.value,
    )
    db.add(job)
    try:
        await db.flush()
    except IntegrityError:
        # Garde-fou : l'index unique partiel a refuse un doublon que le verrou du document
        # aurait du empecher (une ecriture hors de cet endpoint). On rend le job qui existe.
        await db.rollback()
        raced = (
            await db.execute(
                select(Job)
                .where(Job.document_id == payload.document_id)
                .where(Job.agent_id == payload.agent_id)
                .where(Job.state != JobState.CANCELLED.value)
                .order_by(Job.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if raced is None:
            raise
        response.status_code = 200
        return _job_created_out(raced)
    return _job_created_out(job)


def _ensure_job_agent(job: Job, caller: Caller) -> None:
    """Seul l'operateur du job ecrit dessus (propositions, submit).

    Ni un autre operateur, ni un role transverse, ni un service : une proposition ou un submit
    fait au nom d'un autre fausserait le consensus, qui suppose des avis independants.
    """
    if isinstance(caller, UserCaller) and caller.user_id == job.agent_id:
        return
    raise HTTPException(status_code=403, detail="Job reserve a son operateur")


def _ensure_open(job: Job) -> None:
    if job.state == JobState.SUBMITTED.value:
        raise_conflict(Job, "deja soumis")
    if job.state == JobState.CANCELLED.value:
        raise_conflict(Job, "annule")


def _start_if_assigned(job: Job) -> None:
    """Le premier travail de l'operateur fait passer le job en IN_PROGRESS."""
    if job.state == JobState.ASSIGNED.value:
        job.state = JobState.IN_PROGRESS.value
        job.started_at = datetime.now(timezone.utc)


def _apply_proposal(
    db: AsyncSession,
    job: Job,
    payload: FieldProposalIn,
    existing: Optional[FieldProposal],
) -> FieldProposal:
    """Cree ou met a jour la proposition de l'operateur.

    Le DocumentField partage n'est PAS modifie : la valeur retenue est celle du consensus
    (services/consensus.py). Y reporter chaque proposition faisait voir au second operateur la
    valeur du premier avant son propre avis, et ce n'est plus utile : l'IHM lit les propositions
    du job.
    """
    if existing:
        existing.value = payload.value
        # value_type est NOT NULL : une re-proposition qui ne le renvoie pas
        # (ex. widget radio) ne doit pas ecraser le type deja enregistre.
        if payload.value_type is not None:
            existing.value_type = payload.value_type
        existing.reason = payload.reason
        proposal = existing
    else:
        proposal = FieldProposal(
            job_id=job.id,
            document_field_id=payload.document_field_id,
            step=job.step,
            value=payload.value,
            value_type=payload.value_type or FieldValueType.TEXT.value,
            reason=payload.reason,
        )
        db.add(proposal)
    return proposal


def _proposal_out(proposal: FieldProposal, document_field_id: int) -> FieldProposalOut:
    return FieldProposalOut(
        id=proposal.id,
        job_id=proposal.job_id,
        document_field_id=document_field_id,
        step=proposal.step,
        value=proposal.value,
        value_type=proposal.value_type,
    )


@router.post("/{job_id}/propose", status_code=201, responses=_AGENT_ONLY)
async def propose_field_value(
    job_id: int,
    payload: FieldProposalIn,
    db: AsyncSession = Depends(get_db),
    caller: Caller = Depends(get_caller),
) -> FieldProposalOut:
    """Soumet ou met a jour la proposition de valeur d'un operateur sur un champ.

    Passe automatiquement le job en IN_PROGRESS au premier appel.
    """
    job = await db.get(Job, job_id)
    if not job:
        raise_not_found(Job)
    _ensure_job_agent(job, caller)
    _ensure_open(job)

    df = await db.get(DocumentField, payload.document_field_id)
    if not df:
        raise_not_found(DocumentField)
    if df.document_id != job.document_id:
        raise_unprocessable("Champ etranger au document du job")

    _start_if_assigned(job)

    existing = (
        await db.execute(
            select(FieldProposal)
            .where(FieldProposal.job_id == job_id)
            .where(FieldProposal.document_field_id == payload.document_field_id)
        )
    ).scalar_one_or_none()

    proposal = _apply_proposal(db, job, payload, existing)
    await db.flush()
    return FieldProposalOut(
        id=proposal.id,
        job_id=job_id,
        document_field_id=payload.document_field_id,
        step=proposal.step,
        value=proposal.value,
        value_type=proposal.value_type,
    )


@router.post("/{job_id}/propose/bulk", status_code=201, responses=_AGENT_ONLY)
async def propose_field_values(
    job_id: int,
    payload: FieldProposalBulkIn,
    db: AsyncSession = Depends(get_db),
    caller: Caller = Depends(get_caller),
) -> List[FieldProposalOut]:
    """Propose plusieurs valeurs en une transaction (ex. valider une section entiere).

    Tout ou rien : un champ inconnu (404) ou etranger au document du job (422) fait echouer
    le lot sans rien ecrire. Un meme champ present plusieurs fois garde sa derniere valeur.
    """
    job = await db.get(Job, job_id)
    if not job:
        raise_not_found(Job)
    _ensure_job_agent(job, caller)
    _ensure_open(job)

    wanted = {p.document_field_id: p for p in payload.proposals}
    fields = (
        (await db.execute(select(DocumentField).where(DocumentField.id.in_(list(wanted)))))
        .scalars()
        .all()
    )
    by_id = {df.id: df for df in fields}
    missing = sorted(set(wanted) - set(by_id))
    if missing:
        raise_not_found(DocumentField, f"Champs introuvables : {missing}")
    foreign = sorted(i for i, df in by_id.items() if df.document_id != job.document_id)
    if foreign:
        raise_unprocessable(f"Champs etrangers au document du job : {foreign}")

    existing = {
        p.document_field_id: p
        for p in (
            await db.execute(
                select(FieldProposal)
                .where(FieldProposal.job_id == job_id)
                .where(FieldProposal.document_field_id.in_(list(wanted)))
            )
        )
        .scalars()
        .all()
    }

    _start_if_assigned(job)
    saved = [
        (field_id, _apply_proposal(db, job, item, existing.get(field_id)))
        for field_id, item in wanted.items()
    ]
    await db.flush()
    return [_proposal_out(proposal, field_id) for field_id, proposal in saved]


# PATCH


@router.patch("/{job_id}/submit", responses=_AGENT_ONLY)
async def submit_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    caller: Caller = Depends(get_caller),
) -> JobSubmitOut:
    """Finalise le job, donc l'operateur ne peut plus modifier ses proposals.

    Passe l'etat a SUBMITTED et enregistre submitted_at.
    Declenche try_resolve en background si le nombre de jobs SUBMITTED atteint
    required_operators du dataset.

    Deux garanties, que ce simple enchainement ne donnait pas :

    - Le consensus voit le submit. La tache de fond s'execute avant la fermeture de la session
      de la requete, donc avant son commit : lancee telle quelle, elle comptait un job de moins
      que le quorum et le document restait PENDING_CONSENSUS a vie. Le commit est donc fait
      ici, avant de planifier la tache.
    - Un submit a la fois par document. Le job puis le document sont verrouilles
      (SELECT ... FOR UPDATE) : deux submits simultanes du meme job donnent 200 puis 409, et
      deux operateurs qui soumettent en meme temps voient chacun l'autre, au lieu de compter
      tous deux "1/2" et de ne jamais declencher le consensus.
    """
    job = await db.get(Job, job_id, with_for_update=True)
    if not job:
        raise_not_found(Job)
    _ensure_job_agent(job, caller)
    if job.state == JobState.SUBMITTED.value:
        raise_conflict(Job, "deja soumis")
    if job.state == JobState.CANCELLED.value:
        raise_conflict(Job, "deja annule")

    document = await db.get(Document, job.document_id, with_for_update=True)

    # Un champ qui porte une valeur (OCR ou saisie) doit avoir ete revu par l'operateur : sans
    # proposition, le consensus retiendrait la valeur OCR comme si elle avait ete controlee.
    # C'est la regle que l'IHM applique deja ("champs a corriger"), tenue ici cote serveur. Un
    # champ en litige doit toujours etre tranche, meme vide (deux avis opposes sur un champ
    # sans valeur OCR). Les autres champs vides n'ont pas besoin de proposition, ni ceux que le
    # consensus a deja tranches.
    unreviewed: int = (
        await db.execute(
            select(count(DocumentField.id))
            .where(DocumentField.document_id == job.document_id)
            .where(DocumentField.consensus_reached.is_(False))
            .where(
                or_(
                    func.coalesce(DocumentField.resolved_value, "") != "",
                    func.coalesce(DocumentField.ocr_value, "") != "",
                    DocumentField.status == DocumentFieldStatus.DISPUTED.value,
                )
            )
            .where(
                ~DocumentField.id.in_(
                    select(FieldProposal.document_field_id).where(FieldProposal.job_id == job_id)
                )
            )
        )
    ).scalar_one() or 0
    if unreviewed:
        raise_conflict(Job, f"{unreviewed} champ(s) a revoir (valeur ou litige) sans proposition")

    job.state = JobState.SUBMITTED.value
    job.submitted_at = datetime.now(timezone.utc)
    await db.flush()

    submitted_count: int = (
        await db.execute(
            select(count(Job.id))
            .where(Job.document_id == job.document_id)
            .where(Job.state == JobState.SUBMITTED.value)
        )
    ).scalar_one() or 0

    dataset = await db.get(Dataset, job.dataset_id)
    quorum_reached = bool(dataset and submitted_count >= dataset.required_operators)
    if (
        quorum_reached
        and document
        and document.status
        not in (
            DocumentStatus.VALIDATED.value,
            DocumentStatus.EXPORTED.value,
        )
    ):
        document.status = DocumentStatus.PENDING_CONSENSUS.value

    logger.info(
        "consensus declenche [document_id=%s jobs=%s/%s]",
        job.document_id,
        submitted_count,
        dataset.required_operators if dataset else "?",
    )
    result = JobSubmitOut(
        id=job.id,
        state=job.state,
        step=job.step,
        submitted_at=job.submitted_at,
    )
    document_id, dataset_id = job.document_id, job.dataset_id
    if quorum_reached:
        # Visible des autres sessions avant que la tache de fond ne la lise.
        await db.commit()
        background_tasks.add_task(try_resolve, document_id, dataset_id)
    return result
