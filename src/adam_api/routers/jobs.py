"""Jobs - tache de labellisation par operateur.

Un job represente une tache de labellisation assignee a un operateur sur un document.
Chaque document passe par deux etapes : validation puis consensus.

GET   : liste des jobs, detail avec champs structures par page/section
POST  : creation d'un job, proposition de valeur, soumission
PATCH : finalisation (submit)
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.functions import count

from adam_api.dependencies.db import get_db
from adam_api.services.consensus import try_resolve
from adam_core.enums.status import DocumentFieldStatus, DocumentStatus, JobState, JobStep
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
from adam_core.utils.exceptions import raise_conflict, raise_not_found
from adam_core.utils.logging import get_logger

router = APIRouter(prefix="/jobs", tags=["Jobs"])
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


@router.get("/{job_id}", response_model=JobDetailOut)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)) -> JobDetailOut:
    """Detail d'un job avec les champs du document structures par page puis section.

    Inclut la proposal de cet operateur sur chaque champ si elle existe.
    Point d'entree principal de l'IHM labellisation.
    """
    result = await db.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(
            selectinload(Job.document).selectinload(Document.document_fields).selectinload(DocumentField.field_spec),
            selectinload(Job.field_proposals),
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise_not_found(Job)

    proposal_index = {p.document_field_id: p for p in job.field_proposals}

    pages: dict = {}
    for df in job.document.document_fields:
        fs = df.field_spec
        page_num = fs.page if fs else 0
        pages.setdefault(page_num, {"page": page_num, "sections": {}})
        sec_id = fs.section_id if fs else "unknown"
        if sec_id not in pages[page_num]["sections"]:
            pages[page_num]["sections"][sec_id] = JobSectionOut(
                section_id=sec_id,
                section_label=fs.section_label if fs else None,
                fields=[],
            )
        proposal = proposal_index.get(df.id)
        pages[page_num]["sections"][sec_id].fields.append(
            JobFieldItemOut(
                id=df.id,
                field_key=fs.field_key if fs else None,
                step=job.step,
                value=proposal.value if proposal else None,
                value_type=proposal.value_type if proposal else None,
                reason=proposal.reason if proposal else None,
            )
        )

    sorted_pages = [
        JobPageOut(page=p["page"], sections=list(p["sections"].values()))
        for p in sorted(pages.values(), key=lambda x: x["page"])
    ]

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

@router.post("", response_model=JobCreatedOut, status_code=201)
async def create_job(payload: JobIn, db: AsyncSession = Depends(get_db)) -> JobCreatedOut:
    """Cree un job et l'assigne a un operateur."""
    doc = await db.get(Document, payload.document_id)
    if not doc:
        raise_not_found(Document)

    agent = await db.get(User, payload.agent_id)
    if not agent:
        raise_not_found(User)

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
    await db.flush()
    return JobCreatedOut(
        id=job.id,
        step=job.step,
        state=job.state,
        agent_id=job.agent_id,
        document_id=job.document_id,
        dataset_id=job.dataset_id,
    )


@router.post("/{job_id}/propose", response_model=FieldProposalOut, status_code=201)
async def propose_field_value(
    job_id: int,
    payload: FieldProposalIn,
    db: AsyncSession = Depends(get_db),
) -> FieldProposalOut:
    """Soumet ou met a jour la proposition de valeur d'un operateur sur un champ.

    Passe automatiquement le job en IN_PROGRESS au premier appel.
    """
    job = await db.get(Job, job_id)
    if not job:
        raise_not_found(Job)
    if job.state == JobState.SUBMITTED.value:
        raise_conflict(Job, "deja soumis")
    if job.state == JobState.CANCELLED.value:
        raise_conflict(Job, "annule")

    df = await db.get(DocumentField, payload.document_field_id)
    if not df:
        raise_not_found(DocumentField)

    if job.state == JobState.ASSIGNED.value:
        job.state = JobState.IN_PROGRESS.value
        job.started_at = datetime.now(timezone.utc)

    existing = (
        await db.execute(
            select(FieldProposal)
            .where(FieldProposal.job_id == job_id)
            .where(FieldProposal.document_field_id == payload.document_field_id)
        )
    ).scalar_one_or_none()

    if existing:
        existing.value = payload.value
        existing.value_type = payload.value_type
        existing.reason = payload.reason
        proposal = existing
    else:
        proposal = FieldProposal(
            job_id=job_id,
            document_field_id=payload.document_field_id,
            step=job.step,
            value=payload.value,
            value_type=payload.value_type or "TEXT",
            reason=payload.reason,
        )
        db.add(proposal)

    df.resolved_value = payload.value
    df.status = DocumentFieldStatus.CORRECTED.value

    await db.flush()
    return FieldProposalOut(
        id=proposal.id,
        job_id=job_id,
        document_field_id=payload.document_field_id,
        step=proposal.step,
        value=proposal.value,
        value_type=proposal.value_type,
    )


# PATCH

@router.patch("/{job_id}/submit", response_model=JobSubmitOut)
async def submit_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> JobSubmitOut:
    """Finalise le job, donc l'operateur ne peut plus modifier ses proposals.

    Passe l'etat a SUBMITTED et enregistre submitted_at.
    Declenche try_resolve en background si le nombre de jobs SUBMITTED atteint
    required_operators du dataset.
    """
    job = await db.get(Job, job_id)
    if not job:
        raise_not_found(Job)
    if job.state == JobState.SUBMITTED.value:
        raise_conflict(Job, "deja soumis")
    if job.state == JobState.CANCELLED.value:
        raise_conflict(Job, "deja annule")

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
    if dataset and submitted_count >= dataset.required_operators:
        doc = await db.get(Document, job.document_id)
        if doc and doc.status not in (
            DocumentStatus.VALIDATED.value,
            DocumentStatus.EXPORTED.value,
        ):
            doc.status = DocumentStatus.PENDING_CONSENSUS.value

    logger.info(
        "consensus declenche [document_id=%s jobs=%s/%s]",
        job.document_id,
        submitted_count,
        dataset.required_operators if dataset else "?",
    )
    background_tasks.add_task(try_resolve, job.document_id, job.dataset_id)

    return JobSubmitOut(
        id=job.id,
        state=job.state,
        step=job.step,
        submitted_at=job.submitted_at,
    )
