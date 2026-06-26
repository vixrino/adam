"""Documents - GET/POST/PATCH endpoints."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from adam_api.dependencies.db import get_db
from adam_core.enums.status import DocumentFieldStatus, DocumentStatus
from adam_core.models import Document, DocumentField
from adam_core.schemas.responses import (
    DocumentFieldOut,
    DocumentFieldPatchOut,
    DocumentFullOut,
    DocumentOut,
    FileRefOut,
)
from adam_core.utils.exceptions import raise_conflict, raise_not_found

router = APIRouter(prefix="/documents", tags=["Documents"])


class DocumentIn(BaseModel):
    dataset_id: int
    file_id: int
    file_name: str
    metadata: Dict[str, Any] = {}


class DocumentPatch(BaseModel):
    status: str
    expected_current_status: Optional[str] = None


class DocumentFieldPatch(BaseModel):
    resolved_value: Optional[str] = None
    status: Optional[str] = None
    consensus_reached: Optional[bool] = None


@router.get("", response_model=List[DocumentOut])
async def list_documents(
    dataset_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> List[Document]:
    query = select(Document).limit(limit)
    if dataset_id is not None:
        query = query.where(Document.dataset_id == dataset_id)
    if status is not None:
        query = query.where(Document.status == status)
    return list((await db.execute(query)).scalars().all())


@router.get("/{document_id}", response_model=DocumentFullOut)
async def get_document(
    document_id: int,
    view: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> DocumentFullOut:
    if view == "full":
        result = await db.execute(
            select(Document)
            .where(Document.id == document_id)
            .options(
                selectinload(Document.document_fields).selectinload(DocumentField.field_spec),
                selectinload(Document.file),
                selectinload(Document.ocr_results),
                selectinload(Document.jobs),
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            raise_not_found(Document)
        pages: Dict[int, Dict[str, Any]] = {}
        for df in doc.document_fields:
            fs = df.field_spec
            page_num = fs.page if fs else 0
            pages.setdefault(page_num, {"page_number": page_num, "sections": {}})
            sec_id = fs.section_id if fs else "unknown"
            pages[page_num]["sections"].setdefault(sec_id, {"id": sec_id, "fields": []})
            pages[page_num]["sections"][sec_id]["fields"].append(
                {
                    "id": df.id,
                    "field_key": fs.field_key if fs else None,
                    "ocr_value": df.ocr_value,
                    "resolved_value": df.resolved_value,
                    "status": df.status,
                }
            )
        file_ref = FileRefOut(id=doc.file.id, path=doc.file.file_path) if doc.file else None
        return DocumentFullOut(
            id=doc.id,
            file_name=doc.file_name,
            status=doc.status,
            metadata=doc.metadata_,
            file=file_ref,
            pages=list(pages.values()),
            ocr_results=[{"id": o.id} for o in doc.ocr_results],
            jobs=[{"id": j.id, "state": j.state} for j in doc.jobs],
        )
    doc = await db.get(Document, document_id)
    if not doc:
        raise_not_found(Document)
    return DocumentFullOut(
        id=doc.id,
        file_name=doc.file_name,
        status=doc.status,
        metadata=doc.metadata_,
    )


@router.get("/{document_id}/fields", response_model=List[DocumentFieldOut])
async def get_document_fields(
    document_id: int, db: AsyncSession = Depends(get_db)
) -> List[DocumentField]:
    rows = list(
        (await db.execute(select(DocumentField).where(DocumentField.document_id == document_id)))
        .scalars()
        .all()
    )
    return rows


@router.get("/{document_id}/fields/by-section", response_model=Dict[str, Any])
async def get_document_fields_by_section(
    document_id: int, db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    result = await db.execute(
        select(DocumentField)
        .where(DocumentField.document_id == document_id)
        .options(selectinload(DocumentField.field_spec))
    )
    sections: Dict[str, list] = {}
    for df in result.scalars().all():
        sec = df.field_spec.section_id if df.field_spec else "unknown"
        sections.setdefault(sec, []).append(
            {"id": df.id, "field_key": df.field_spec.field_key if df.field_spec else None}
        )
    return {"document_id": document_id, "sections": sections}


@router.post("", response_model=DocumentOut, status_code=201)
async def create_document(body: DocumentIn, db: AsyncSession = Depends(get_db)) -> Document:
    doc = Document(
        dataset_id=body.dataset_id,
        file_id=body.file_id,
        file_name=body.file_name,
        metadata_=body.metadata,
    )
    db.add(doc)
    await db.flush()
    return doc


@router.patch("/{document_id}", response_model=DocumentOut)
async def patch_document(
    document_id: int, body: DocumentPatch, db: AsyncSession = Depends(get_db)
) -> Document:
    doc = await db.get(Document, document_id)
    if not doc:
        raise_not_found(Document)
    if body.expected_current_status and doc.status != body.expected_current_status:
        raise_conflict(Document, "Conflit de statut")
    doc.status = body.status
    await db.flush()
    return doc


@router.patch("/{document_id}/fields/{field_id}", response_model=DocumentFieldPatchOut)
async def patch_document_field(
    document_id: int,
    field_id: int,
    body: DocumentFieldPatch,
    db: AsyncSession = Depends(get_db),
) -> DocumentFieldPatchOut:
    df = await db.get(DocumentField, field_id)
    if not df or df.document_id != document_id:
        raise_not_found(DocumentField)
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(df, key, val)
    await db.flush()
    return DocumentFieldPatchOut(id=df.id, status=df.status, resolved_value=df.resolved_value)
