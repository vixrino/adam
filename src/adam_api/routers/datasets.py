"""Datasets - Cree par les admins metier via CLI."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File as UploadField, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from adam_api.core.config import settings
from adam_api.dependencies.db import get_db
from adam_api.services.ingestion import ingest_pdf, looks_like_pdf
from adam_core.enums.ocr import OcrProvider
from adam_core.enums.status import DatasetStatus, DocumentStatus
from adam_core.models import Dataset, DocSchema, Document, Organisation, Project
from adam_core.schemas.responses import DatasetOut, DatasetStatsOut, IngestionOut, FileIngestionItemOut
from adam_core.utils.exceptions import raise_not_found, raise_unprocessable
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
    configs: Dict[str, Any] = Field(default_factory=dict)


class DatasetPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    required_operators: Optional[int] = Field(default=None, ge=1, le=5)
    ocr_job_enabled: Optional[bool] = None
    configs: Optional[Dict[str, Any]] = None


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
    return DatasetStatsOut(dataset_id=dataset_id, documents_total=total, documents_validated=validated)


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
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(row, key, val)
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
    row.status = status
    await db.flush()
    return row


@router.post("/{dataset_id}/documents", response_model=IngestionOut)
async def ingest_documents(
    dataset_id: int,
    files: List[UploadFile] = UploadField(..., description="Un ou plusieurs fichiers PDF"),
    db: AsyncSession = Depends(get_db),
) -> IngestionOut:
    """Ingestion multipart de PDF bruts vers le PVC (statut RECEIVED).

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
            logger.warning("Fichier ignore (non PDF) [dataset_id=%s file_name=%s]", dataset_id, file_name)
            items.append(FileIngestionItemOut(file_name=file_name, status="rejected", reason="non-PDF"))
            continue
        raw = await ingest_pdf(
            db,
            dataset,
            organisation_slug=organisation.slug,
            document_type=schema.document_type,
            file_name=file_name,
            content=content,
            pvc_root=pvc_root,
        )
        items.append(FileIngestionItemOut(**raw))

    return IngestionOut(
        dataset_id=dataset_id,
        received=len(items),
        created=sum(1 for r in items if r.status in ("created", "created_file_reused")),
        already_exists=sum(1 for r in items if r.status == "already_exists"),
        rejected=sum(1 for r in items if r.status == "rejected"),
        results=items,
    )
