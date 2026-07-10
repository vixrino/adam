"""
Files
Un File est fichier physique sur PVC.
Plusieurs Documents peuvent pointer vers le meme File.
GET  : lecture simple, enrichie, et des documents utilisant le fichier
POST : creation d'un fichier
PATCH: mise a jour en cas de deplacement du fichier
"""

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from adam_api.core.config import settings
from adam_api.dependencies.db import get_db
from adam_core.models import Document, File
from adam_core.schemas.responses import (
    DocumentOut,
    FileCreatedOut,
    FileDetailOut,
    FileOut,
    FilePatchOut,
)
from adam_core.utils.exceptions import raise_not_found

router = APIRouter(prefix="/files", tags=["Files"])


# Schemas Pydantic

class FileIn(BaseModel):
    file_path: str
    sha256_checksum: str = Field(min_length=64, max_length=64)
    file_size_bytes: int = Field(gt=0)
    page_count: int = Field(default=1, ge=1)
    mime_type: str = Field(default="application/pdf")
    storage_type: str = Field(default="pvc")


class FilePatch(BaseModel):
    file_path: Optional[str] = None  # si le fichier est deplace sur le PVC
    page_count: Optional[int] = Field(default=None, ge=1)


# GET

@router.get("", response_model=List[FileOut])
async def list_files(
    storage_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> List[File]:
    query = select(File)
    if storage_type:
        query = query.where(File.storage_type == storage_type)
    return list((await db.execute(query)).scalars().all())


@router.get("/{file_id}", response_model=FileDetailOut)
async def get_file(file_id: int, db: AsyncSession = Depends(get_db)) -> FileDetailOut:
    result = await db.execute(
        select(File).where(File.id == file_id).options(selectinload(File.documents))
    )
    file = result.scalar_one_or_none()
    if not file:
        raise_not_found(File)
    return FileDetailOut(
        id=file.id,
        file_path=file.file_path,
        storage_type=file.storage_type,
        mime_type=file.mime_type,
        page_count=file.page_count,
        file_size_bytes=file.file_size_bytes,
        sha256_checksum=file.sha256_checksum,
        created_at=file.created_at,
        documents_count=len(file.documents),
    )


@router.get("/{file_id}/content")
async def get_file_content(file_id: int, db: AsyncSession = Depends(get_db)) -> FileResponse:
    """Retourne les octets bruts du fichier physique (PDF), pour visualisation/telechargement."""
    file = await db.get(File, file_id)
    if not file:
        raise_not_found(File)
    abs_path = Path(settings.pvc_mount_path) / file.file_path
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="Fichier absent du PVC")
    return FileResponse(abs_path, media_type=file.mime_type, filename=abs_path.name)


@router.get("/{file_id}/documents", response_model=List[DocumentOut])
async def get_file_documents(file_id: int, db: AsyncSession = Depends(get_db)) -> List[Document]:
    """Tous les documents qui referencent ce fichier physique."""
    file = await db.get(File, file_id)
    if not file:
        raise_not_found(File)
    rows = (await db.execute(select(Document).where(Document.file_id == file_id))).scalars().all()
    return list(rows)


# POST

@router.post("", response_model=FileCreatedOut, status_code=201)
async def create_file(
    payload: FileIn, response: Response, db: AsyncSession = Depends(get_db)
) -> FileCreatedOut:
    """Cree un fichier physique.

    Si le sha256 existe deja, retourne le fichier existant (deduplication).
    """
    existing = (
        await db.execute(select(File).where(File.sha256_checksum == payload.sha256_checksum))
    ).scalar_one_or_none()

    if existing:
        response.status_code = 200  # deduplication est consideree comme 200
        return FileCreatedOut(
            id=existing.id,
            file_path=existing.file_path,
            sha256_checksum=existing.sha256_checksum,
            deduplicated=True,
        )

    file = File(
        file_path=payload.file_path,
        sha256_checksum=payload.sha256_checksum,
        file_size_bytes=payload.file_size_bytes,
        page_count=payload.page_count,
        mime_type=payload.mime_type,
        storage_type=payload.storage_type,
    )
    db.add(file)
    await db.flush()
    return FileCreatedOut(
        id=file.id,
        file_path=file.file_path,
        sha256_checksum=file.sha256_checksum,
        deduplicated=False,
    )


# PATCH

@router.patch("/{file_id}", response_model=FilePatchOut)
async def patch_file(
    file_id: int,
    payload: FilePatch,
    db: AsyncSession = Depends(get_db),
) -> FilePatchOut:
    """Met a jour les metadonnees d'un fichier.

    Utile si le fichier est deplace sur le PVC ou si le page_count est corrige.
    Le sha256 et file_size_bytes sont immuables.
    """
    file = await db.get(File, file_id)
    if not file:
        raise_not_found(File)
    if payload.file_path is not None:
        file.file_path = payload.file_path
    if payload.page_count is not None:
        file.page_count = payload.page_count
    await db.flush()
    return FilePatchOut(id=file.id, file_path=file.file_path, page_count=file.page_count)
