"""Resultats OCR - GET/POST."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.db import get_db
from adam_core.enums.ocr import StorageMode
from adam_core.enums.status import DocumentFieldStatus
from adam_core.models import Document, DocumentField, FieldSpec, OcrResult
from adam_core.schemas.interface_contract import FormDocument
from adam_core.utils.exceptions import raise_not_found

router = APIRouter(prefix="/ocr-results", tags=["OCR"])


class OcrResultIn(BaseModel):
    document_id: int
    dataset_id: int
    raw_json: Dict[str, Any]
    storage_mode: str = Field(default=StorageMode.JSONB.value)


@router.get("", response_model=List[Dict[str, Any]])
async def list_ocr_results(
    document_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    query = select(OcrResult)
    if document_id is not None:
        query = query.where(OcrResult.document_id == document_id)
    rows = (await db.execute(query)).scalars().all()
    return [{"id": r.id, "document_id": r.document_id, "dataset_id": r.dataset_id} for r in rows]


@router.get("/{ocr_id}", response_model=Dict[str, Any])
async def get_ocr_result(ocr_id: int, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    row = await db.get(OcrResult, ocr_id)
    if not row:
        raise_not_found(OcrResult)
    return {"id": row.id, "document_id": row.document_id, "storage_mode": row.storage_mode}


@router.post("", response_model=Dict[str, Any], status_code=201)
async def post_ocr_result(body: OcrResultIn, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    form_doc = FormDocument.model_validate(body.raw_json)
    ocr = OcrResult(
        document_id=body.document_id,
        dataset_id=body.dataset_id,
        storage_mode=body.storage_mode,
        raw_json=body.raw_json,
    )
    db.add(ocr)
    await db.flush()
    doc = await db.get(Document, body.document_id)
    if not doc:
        raise_not_found(Document)
    specs = (
        await db.execute(select(FieldSpec).where(FieldSpec.schema_id == doc.dataset.schema_id))
    ).scalars().all() if doc.dataset else []
    spec_index = {(s.section_id, s.field_key): s for s in specs}
    created = 0
    for _, section, kv in form_doc.iter_kv_pairs():
        fs = spec_index.get((section.id, kv.field_key))
        if not fs:
            continue
        df = DocumentField(
            document_id=body.document_id,
            field_spec_id=fs.id,
            group_id=kv.group_id,
            ocr_value=kv.extracted_value,
            resolved_value=kv.extracted_value,
            status=DocumentFieldStatus.PENDING.value,
            ocr_confidence=kv.confidence,
            ocr_polygon=kv.polygon,
        )
        db.add(df)
        created += 1
    await db.flush()
    return {"id": ocr.id, "document_fields_created": created}
