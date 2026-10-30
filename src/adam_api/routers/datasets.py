"""Datasets - Cree par les admins metier via CLI."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, File as UploadField, HTTPException, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from adam_api.core.config import settings
from adam_api.dependencies.auth import Caller, UserCaller, get_caller
from adam_api.dependencies.db import get_db
from adam_api.services.ingestion import ingest_pdf, looks_like_pdf
from adam_core.enums.ocr import OcrProvider
from adam_core.enums.roles import CROSS_ORGANISATION_ROLE_VALUES, ProjectRole
from adam_core.enums.status import DatasetStatus, DocumentStatus, JobState
from adam_core.models import (
    Dataset,
    DocSchema,
    Document,
    FieldSpec,
    Job,
    Organisation,
    Project,
    User,
    UserProject,
)
from adam_core.schemas.responses import (
    DatasetOut,
    DatasetStatsOut,
    FileIngestionItemOut,
    IngestionOut,
)
from adam_core.utils.exceptions import raise_conflict, raise_not_found, raise_unprocessable
from adam_core.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/datasets", tags=["Datasets"])


class DatasetIn(BaseModel):
    project_id: int
    schema_id: int
    name: str
    description: Optional[str] = None
    ocr_provider: str = OcrProvider.PULSAR.value
    ocr_model_id: Optional[str] = None
    required_operators: int = Field(default=3, ge=1, le=5)
    ocr_job_enabled: bool = True
    #: Nombre de pages exige des PDF ingeres ; None = aucun controle.
    expected_page_count: Optional[int] = Field(default=None, ge=1)
    configs: Dict[str, Any] = Field(default_factory=dict)


class DatasetPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    required_operators: Optional[int] = Field(default=None, ge=1, le=5)
    ocr_job_enabled: Optional[bool] = None
    expected_page_count: Optional[int] = Field(default=None, ge=1)
    configs: Optional[Dict[str, Any]] = None
    schema_id: Optional[int] = None


#: Cycle de vie d'un dataset : ce qu'on peut atteindre depuis chaque etat.
#:
#: DRAFT est l'etat de preparation. Le schema reste modifiable tant qu'aucun
#: dataset ne l'a quitte — c'est la regle que fait respecter
#: _check_schema_not_locked, dans routers/schemas.py.
#:
#: ACTIVE ne revient pas a DRAFT. Le retour deverrouillerait le schema alors que
#: des documents ont pu etre annotes avec : les DOCUMENT_FIELD deja crees
#: pointeraient vers des FIELD_SPEC redevenus modifiables, et une correction du
#: schema changerait retroactivement le sens de ce qui a ete saisi. Un dataset
#: qu'on veut reprendre s'archive, et un nouveau prend sa suite.
#:
#: ARCHIVED est terminal. Desarchiver rouvrirait la meme question sans la
#: resoudre : soit le perimetre est fige et le dataset reste utilisable en
#: lecture, soit il change et c'est un autre dataset.
_ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    DatasetStatus.DRAFT.value: {DatasetStatus.ACTIVE.value, DatasetStatus.ARCHIVED.value},
    DatasetStatus.ACTIVE.value: {DatasetStatus.ARCHIVED.value},
    DatasetStatus.ARCHIVED.value: set(),
}


async def _check_ready_for_activation(dataset: Dataset, db: AsyncSession) -> DocSchema:
    """Refuse l'activation d'un dataset dont le schema ne decrit aucun champ.

    Activer, c'est ouvrir le lot aux operateurs et figer le schema. Un schema
    sans FIELD_SPEC leur presenterait des documents sans rien a annoter, et le
    verrou interdirait ensuite d'y ajouter les champs manquants : le lot serait
    inutilisable et irreparable en meme temps.

    Rend le schema, que l'appelant verrouille une fois l'activation acquise.
    """
    schema = await db.get(DocSchema, dataset.schema_id)
    if schema is None:
        raise_unprocessable(
            f"Dataset {dataset.id} : schema {dataset.schema_id} introuvable, activation impossible"
        )
    field_count: int = (
        await db.execute(select(count(FieldSpec.id)).where(FieldSpec.schema_id == schema.id))
    ).scalar_one()
    if field_count == 0:
        raise_unprocessable(
            f"Le schema '{schema.name}' ne declare aucun champ : "
            "activer le dataset le figerait sans rien a annoter"
        )
    return schema


async def _apply_status_transition(dataset: Dataset, target: str, db: AsyncSession) -> None:
    """Fait passer le dataset a `target`, si le cycle de vie l'autorise.

    Reposer le statut courant ne fait rien et ne leve pas : un client qui rejoue
    sa requete ne doit pas recevoir un conflit pour un etat deja atteint.
    """
    if target not in {s.value for s in DatasetStatus}:
        raise_unprocessable(f"Statut invalide: {target}")
    if target == dataset.status:
        return
    if target not in _ALLOWED_TRANSITIONS.get(dataset.status, frozenset()):
        raise_conflict(
            Dataset,
            f"transition {dataset.status} -> {target} interdite",
        )
    if target == DatasetStatus.ACTIVE.value:
        # Le verrou implicite (_check_schema_not_locked) devient explicite : le
        # `locked` rendu par l'API dit la verite, sans attendre un 423.
        (await _check_ready_for_activation(dataset, db)).locked = True
    dataset.status = target


@router.get("", response_model=List[DatasetOut])
async def list_datasets(
    project_id: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> List[Dataset]:
    query = select(Dataset)
    if project_id is not None:
        query = query.where(Dataset.project_id == project_id)
    if status is not None:
        query = query.where(Dataset.status == status)
    return list((await db.execute(query)).scalars().all())


@router.get("/{dataset_id}", response_model=DatasetOut)
async def get_dataset(dataset_id: int, db: AsyncSession = Depends(get_db)) -> Dataset:
    row = await db.get(Dataset, dataset_id)
    if not row:
        raise_not_found(Dataset)
    return row


@router.get("/{dataset_id}/stats", response_model=DatasetStatsOut)
async def get_dataset_stats(dataset_id: int, db: AsyncSession = Depends(get_db)) -> DatasetStatsOut:
    row = await db.get(Dataset, dataset_id)
    if not row:
        raise_not_found(Dataset)
    total = (
        await db.execute(select(count(Document.id)).where(Document.dataset_id == dataset_id))
    ).scalar_one()
    validated = (
        await db.execute(
            select(count(Document.id))
            .where(Document.dataset_id == dataset_id)
            .where(Document.status == DocumentStatus.VALIDATED.value)
        )
    ).scalar_one()
    return DatasetStatsOut(
        dataset_id=dataset_id, documents_total=total, documents_validated=validated
    )


@router.post("", response_model=DatasetOut, status_code=201)
async def create_dataset(body: DatasetIn, db: AsyncSession = Depends(get_db)) -> Dataset:
    row = Dataset(**body.model_dump())
    db.add(row)
    await db.flush()
    return row


@router.patch("/{dataset_id}", response_model=DatasetOut)
async def patch_dataset(
    dataset_id: int, body: DatasetPatch, db: AsyncSession = Depends(get_db)
) -> Dataset:
    row = await db.get(Dataset, dataset_id)
    if not row:
        raise_not_found(Dataset)

    updates = body.model_dump(exclude_unset=True)
    if "schema_id" in updates and updates["schema_id"] != row.schema_id:
        if row.status != DatasetStatus.DRAFT.value:
            raise_conflict(
                Dataset,
                "Le schema ne peut changer que sur un dataset DRAFT "
                f"(status={row.status}) : un dataset actif fige son schema",
            )
        new_schema = await db.get(DocSchema, updates["schema_id"])
        if not new_schema:
            raise_not_found(DocSchema)
        existing_documents = (
            await db.execute(select(count(Document.id)).where(Document.dataset_id == dataset_id))
        ).scalar_one()
        if existing_documents > 0:
            raise_unprocessable(
                "Impossible de changer le schema d'un dataset contenant deja des documents"
            )
    target_status = updates.pop("status", None)
    for key, val in updates.items():
        setattr(row, key, val)
    if target_status is not None:
        await _apply_status_transition(row, target_status, db)
    await db.flush()
    return row


@router.patch("/{dataset_id}/status", response_model=DatasetOut)
async def patch_dataset_status(
    dataset_id: int, status: str, db: AsyncSession = Depends(get_db)
) -> Dataset:
    if status not in {s.value for s in DatasetStatus}:
        raise_unprocessable(f"Statut invalide: {status}")
    row = await db.get(Dataset, dataset_id)
    if not row:
        raise_not_found(Dataset)
    await _apply_status_transition(row, status, db)
    await db.flush()
    return row


@router.post("/{dataset_id}/documents", response_model=IngestionOut)
async def ingest_documents(
    dataset_id: int,
    files: List[UploadFile] = UploadField(..., description="Un ou plusieurs fichiers PDF"),
    db: AsyncSession = Depends(get_db),
) -> IngestionOut:
    """Ingestion multipart de PDF bruts vers le PVC (statut RECEIVED).

    Un PDF qui n'a pas le nombre de pages exige par le dataset
    (expected_page_count) est cree en ERROR (statut "error" dans le detail,
    motif dans reason).

    Repond 200 dans tous les cas (y compris doublons), avec un detail par
    fichier. 404 si le dataset n'existe pas.
    """
    dataset = await db.get(Dataset, dataset_id)
    if not dataset:
        raise_not_found(Dataset)

    schema = await db.get(DocSchema, dataset.schema_id)
    project = await db.get(Project, dataset.project_id)
    organisation = await db.get(Organisation, project.organisation_id) if project else None
    if not schema or not organisation:
        raise_unprocessable("Dataset rattache a un schema ou une organisation introuvable")

    pvc_root = Path(settings.pvc_mount_path)
    items: List[FileIngestionItemOut] = []
    for upload in files:
        file_name = upload.filename or "sans_nom.pdf"
        content = await upload.read()
        if not looks_like_pdf(content):
            logger.warning(
                "Fichier ignore (non PDF) [dataset_id=%s file_name=%s]", dataset_id, file_name
            )
            items.append(
                FileIngestionItemOut(file_name=file_name, status="rejected", reason="non-PDF")
            )
            continue
        raw = await ingest_pdf(
            db,
            dataset,
            organisation_slug=organisation.slug,
            document_type=schema.document_type,
            file_name=file_name,
            content=content,
            pvc_root=pvc_root,
            expected_page_count=dataset.expected_page_count or 0,
        )
        items.append(FileIngestionItemOut(**raw))

    return IngestionOut(
        dataset_id=dataset_id,
        received=len(items),
        created=sum(1 for r in items if r.status in ("created", "created_file_reused")),
        already_exists=sum(1 for r in items if r.status == "already_exists"),
        rejected=sum(1 for r in items if r.status == "rejected"),
        in_error=sum(1 for r in items if r.status == "error"),
        results=items,
    )


async def _require_document_remover(
    dataset_id: int,
    caller: Caller = Depends(get_caller),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Reserve le retrait d'un document aux administrateurs.

    Administrateur Metier (BUSINESS_ADMIN) du projet du dataset, ou role de plateforme
    transverse : Administrateur et Superviseur NOTA. Etre BUSINESS_ADMIN d'un autre projet,
    meme de la meme organisation, ne suffit pas. Les services machine sont refuses,
    contrairement a la creation de projet : un worker n'a aucune raison de retirer un
    document, et la cle partagee ne doit pas l'autoriser.
    """
    dataset = await db.get(Dataset, dataset_id)
    if dataset is None:
        raise_not_found(Dataset)
    if isinstance(caller, UserCaller):
        if caller.platform_role in CROSS_ORGANISATION_ROLE_VALUES:
            return
        role = await db.scalar(
            select(UserProject.role)
            .join(User, User.id == UserProject.user_id)
            .where(
                UserProject.project_id == dataset.project_id,
                func.upper(User.matricule) == caller.matricule.upper(),
            )
        )
        if role == ProjectRole.BUSINESS_ADMIN.value:
            return
    raise HTTPException(
        status_code=403,
        detail="Retrait de document reserve aux administrateurs du projet",
    )


@router.delete(
    "/{dataset_id}/documents/{document_id}",
    status_code=204,
    response_model=None,
    response_class=Response,
    dependencies=[Depends(_require_document_remover)],
)
async def remove_document(
    dataset_id: int,
    document_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Retire un document du dataset (symetrique de l'ingestion).

    Suppression definitive, sans soft delete comme les autres : les champs, les jobs et les
    resultats OCR partent avec le document (ON DELETE CASCADE, declare par le modele).
    Le fichier et son contenu sur le PVC restent, la purge relevant de la verification des
    references sur file_id. 403 hors administrateurs, 404 si le document n'appartient pas
    a ce dataset, 409 s'il est exporte ou si un job a deja ete soumis.
    """
    document = await db.get(Document, document_id)
    if document is None or document.dataset_id != dataset_id:
        raise_not_found(Document)
    if document.status == DocumentStatus.EXPORTED.value:
        raise_conflict(Document, "Un document exporte ne peut pas etre retire du dataset")
    # Un job soumis est du travail rendu, et il compte dans le consensus : on ne retire un
    # document que tant qu'aucun operateur n'a soumis. Les jobs non soumis partent avec lui.
    submitted: int = (
        await db.execute(
            select(count(Job.id))
            .where(Job.document_id == document_id)
            .where(Job.state == JobState.SUBMITTED.value)
        )
    ).scalar_one() or 0
    if submitted:
        raise_conflict(
            Document,
            f"{submitted} job(s) soumis : le document ne peut plus etre retire du dataset",
        )
    await db.delete(document)
    await db.flush()
    logger.info(
        "Document retire du dataset [dataset_id=%s document_id=%s]", dataset_id, document_id
    )
