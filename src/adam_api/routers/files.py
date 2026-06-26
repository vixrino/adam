"""Files - fichier physique sur PVC."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.db import get_db
from adam_core.models import Document, File
from adam_core.utils.exceptions import raise_already_exists, raise_not_found

router = APIRouter(prefix="/files", tags=["Files"])


class FileIn(BaseModel):
    file_path: str
    sha256_checksum: str = Field(min_length=64, max_length=64)
    file_size_bytes: int = Field(gt=0)
    page_count: int = Field(default=1, ge=1)
    mime_type: str = Field(default="application/pdf")
    storage_type: str = Field(default="pvc")


class FilePatch(BaseModel):
    file_path: Optional[str] = None
    page_count: Optional[int] = Field(default=None, ge=1)


@router.get("", response_model=List[Dict[str, Any]])
async def list_files(db: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = (await db.execute(select(File))).scalars().all()
    return [{"id": r.id, "file_path": r.file_path, "sha256_checksum": r.sha256_checksum} for r in rows]


@router.get("/{file_id}", response_model=Dict[str, Any])
async def get_file(file_id: int, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    row = await db.get(File, file_id)
    if not row:
        raise_not_found(File)
    return {"id": row.id, "file_path": row.file_path, "page_count": row.page_count}


@router.get("/{file_id}/documents", response_model=List[Dict[str, Any]])
async def get_file_documents(file_id: int, db: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = (await db.execute(select(Document).where(Document.file_id == file_id))).scalars().all()
    return [{"id": r.id, "file_name": r.file_name} for r in rows]


@router.post("", response_model=Dict[str, Any], status_code=201)
async def create_file(body: FileIn, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    existing = (
        await db.execute(select(File).where(File.sha256_checksum == body.sha256_checksum))
    ).scalar_one_or_none()
    if existing:
        raise_already_exists(File)
    row = File(**body.model_dump())
    db.add(row)
    await db.flush()
    return {"id": row.id, "file_path": row.file_path}


@router.patch("/{file_id}", response_model=Dict[str, Any])
async def patch_file(file_id: int, body: FilePatch, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    row = await db.get(File, file_id)
    if not row:
        raise_not_found(File)
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(row, key, val)
    await db.flush()
    return {"id": row.id, "file_path": row.file_path}
