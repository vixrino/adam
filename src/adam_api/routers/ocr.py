"""Resultats OCR
GET : lecture simple
POST : injection d'un resultat OCR (SmartdocDocument)
"""

from typing import Any, Dict, List, Optional, Sequence

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.db import get_db
from adam_core.enums.ocr import StorageMode
from adam_core.enums.status import DocumentFieldStatus, DocumentStatus
from adam_core.models import Dataset, Document, DocumentField, FieldSpec, OcrResult
from adam_core.schemas.interface_contract import SmartdocDocument
from adam_core.schemas.responses import OcrResultCreatedOut, OcrResultDetailOut, OcrResultOut
from adam_core.utils.exceptions import raise_not_found, raise_unprocessable
from adam_core.utils.logging import get_logger

router = APIRouter(prefix="/ocr-results", tags=["OCR"])
logger = get_logger(__name__)


class OcrResultIn(BaseModel):
    document_id: int
    dataset_id: int
    raw_json: Dict[str, Any]
    storage_mode: str = Field(default=StorageMode.JSONB.value)


@router.get("", response_model=List[OcrResultOut])
async def list_ocr_results(
    document_id: Optional[int] = None,
    dataset_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
) -> List[OcrResultOut]:
    """Liste les resultats OCR avec filtres optionnels."""
    query = select(OcrResult)
    if document_id:
        query = query.where(OcrResult.document_id == document_id)
    if dataset_id:
        query = query.where(OcrResult.dataset_id == dataset_id)
    rows = (await db.execute(query)).scalars().all()
    return [
        OcrResultOut(
            id=r.id,
            document_id=r.document_id,
            dataset_id=r.dataset_id,
            storage_mode=r.storage_mode,
            processed_at=r.processed_at,
        )
        for r in rows
    ]


@router.get("/{ocr_result_id}", response_model=OcrResultDetailOut)
async def get_ocr_result(
    ocr_result_id: int, db: AsyncSession = Depends(get_db)
) -> OcrResultDetailOut:
    """Detail d'un OcrResult avec le JSON brut si storage_mode=jsonb."""
    ocr = await db.get(OcrResult, ocr_result_id)
    if not ocr:
        raise_not_found(OcrResult)
    return OcrResultDetailOut(
        id=ocr.id,
        document_id=ocr.document_id,
        dataset_id=ocr.dataset_id,
        storage_mode=ocr.storage_mode,
        processed_at=ocr.processed_at,
        raw_json=ocr.raw_json if ocr.storage_mode == StorageMode.JSONB.value else None,
    )


@router.post("", response_model=OcrResultCreatedOut, status_code=201)
async def post_ocr_result(
    payload: OcrResultIn, db: AsyncSession = Depends(get_db)
) -> OcrResultCreatedOut:
    """
    Insere un resultat OCR et cree les DocumentFields manquants.

    Logique :
    - Tous les champs du schema sont crees, meme si l'OCR ne les a pas extraits
    - Les champs deja presents en base sont ignores (protection doublons)
    - L'OCR peuple ocr_value / ocr_confidence / ocr_polygon quand disponible
    """
    doc = await db.get(Document, payload.document_id)
    if not doc:
        raise_not_found(Document)

    dataset = await db.get(Dataset, payload.dataset_id)
    if not dataset:
        raise_not_found(Dataset)

    try:
        ocr_doc = SmartdocDocument.model_validate(payload.raw_json)
    except ValidationError as e:
        raise_unprocessable(detail=str(e))

    ocr = OcrResult(
        document_id=payload.document_id,
        dataset_id=payload.dataset_id,
        storage_mode=payload.storage_mode,
        raw_json=payload.raw_json,
    )
    db.add(ocr)
    await db.flush()

    all_field_specs: Sequence[FieldSpec] = (
        (await db.execute(select(FieldSpec).where(FieldSpec.schema_id == dataset.schema_id)))
        .scalars()
        .all()
    )

    ocr_index: Dict[tuple[str, str], Any] = {
        (section.id, kv.field_key): kv for _, section, kv in ocr_doc.iter_kv_pairs()
    }

    existing_spec_ids: set[int] = set(
        (
            await db.execute(
                select(DocumentField.field_spec_id).where(
                    DocumentField.document_id == payload.document_id
                )
            )
        )
        .scalars()
        .all()
    )

    doc_fields: list[DocumentField] = []
    for fs in all_field_specs:
        if fs.id in existing_spec_ids:
            continue
        kv = ocr_index.get((fs.section_id, fs.field_key))
        doc_fields.append(
            DocumentField(
                document_id=payload.document_id,
                field_spec_id=fs.id,
                group_id=kv.group_id if kv else None,
                ocr_value=kv.extracted_value if kv else None,
                resolved_value=kv.extracted_value if kv else None,
                status=DocumentFieldStatus.PENDING.value,
                ocr_confidence=kv.confidence if kv else None,
                ocr_polygon=kv.polygon if kv else None,
                consensus_reached=False,
            )
        )

    if doc_fields:
        db.add_all(doc_fields)

    doc.status = DocumentStatus.IN_PROGRESS.value
    await db.flush()

    logger.info(
        "Ocr ingere document_id=%s fields_crees=%s fields_ignores=%s",
        payload.document_id,
        len(doc_fields),
        len(existing_spec_ids),
    )

    return OcrResultCreatedOut(
        ocr_result_id=ocr.id,
        document_fields_created=len(doc_fields),
        document_fields_skipped=len(existing_spec_ids),
        document_status=doc.status,
    )
