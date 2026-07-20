"""Documents - GET/POST/PATCH endpoints."""

from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from adam_api.dependencies.db import get_db
from adam_core.enums.status import DocumentStatus, JobState
from adam_core.models import Document, DocumentField
from adam_core.schemas.responses import (
    DocumentFieldInPageOut,
    DocumentFieldOut,
    DocumentFieldPatchOut,
    DocumentFieldsBySectionOut,
    DocumentFullOut,
    DocumentJobOut,
    DocumentJobProgressOut,
    DocumentOcrResultOut,
    DocumentOut,
    DocumentPageOut,
    DocumentSectionOut,
    FieldBySectionItemOut,
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
    # CA-2 : selectinload(file) pour peupler page_count via Document.page_count
    query = select(Document).options(selectinload(Document.file)).limit(limit)
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

        # Construire les pages avec des schémas typés
        pages_dict: Dict[int, Dict[str, Any]] = {}
        for df in doc.document_fields:
            fs = df.field_spec
            page_num = fs.page if fs else 0
            if page_num not in pages_dict:
                pages_dict[page_num] = {"page_number": page_num, "sections": {}}
            sec_id = fs.section_id if fs else "unknown"
            if sec_id not in pages_dict[page_num]["sections"]:
                pages_dict[page_num]["sections"][sec_id] = {"id": sec_id, "fields": []}
            pages_dict[page_num]["sections"][sec_id]["fields"].append(
                DocumentFieldInPageOut(
                    id=df.id,
                    field_key=fs.field_key if fs else None,
                    ocr_value=df.ocr_value,
                    resolved_value=df.resolved_value,
                    status=df.status,
                )
            )

        pages_list: List[DocumentPageOut] = []
        for page_num, page_data in sorted(pages_dict.items()):
            sections = [
                DocumentSectionOut(id=sec_id, fields=sec_data["fields"])
                for sec_id, sec_data in page_data["sections"].items()
            ]
            pages_list.append(DocumentPageOut(page_number=page_num, sections=sections))

        file_ref = FileRefOut(id=doc.file.id, path=doc.file.file_path) if doc.file else None
        return DocumentFullOut(
            id=doc.id,
            file_name=doc.file_name,
            status=doc.status,
            metadata=doc.metadata_,
            file=file_ref,
            pages=pages_list,
            ocr_results=[DocumentOcrResultOut(id=o.id) for o in doc.ocr_results],
            jobs=[DocumentJobOut(id=j.id, state=j.state) for j in doc.jobs],
            page_count=doc.file.page_count if doc.file else None,
        )

    # Vue simple — CA-2 : charger le fichier pour page_count
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.file))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise_not_found(Document)
    return DocumentFullOut(
        id=doc.id,
        file_name=doc.file_name,
        status=doc.status,
        metadata=doc.metadata_,
        page_count=doc.file.page_count if doc.file else None,
    )


@router.get("/{document_id}/job-progress", response_model=DocumentJobProgressOut)
async def get_document_job_progress(
    document_id: int, db: AsyncSession = Depends(get_db)
) -> DocumentJobProgressOut:
    """Etat du Job actif d'un Document, pour piloter le bouton Continuer du front.

    Un Job actif est un Job non termine (state ASSIGNED ou IN_PROGRESS). CA-4 :
    un Document sans Job actif renvoie 200 avec has_active_job=False, distinct
    du 404 d'un Document introuvable.
    """
    result = await db.execute(
        select(Document).where(Document.id == document_id).options(selectinload(Document.jobs))
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise_not_found(Document)  # CA-4 : distinct du "pas de job actif"

    active_states = {JobState.ASSIGNED.value, JobState.IN_PROGRESS.value}
    active_jobs = [j for j in doc.jobs if j.state in active_states]
    active = max(active_jobs, key=lambda j: j.id, default=None)

    # CA-3 : action exploitable par le front
    action: Literal["CONTINUE", "REVIEW", "UNAVAILABLE"]
    if active is not None:
        action = "CONTINUE"
    elif doc.status in (DocumentStatus.VALIDATED.value, DocumentStatus.EXPORTED.value) or any(
        j.state == JobState.SUBMITTED.value for j in doc.jobs
    ):
        action = "REVIEW"
    else:
        action = "UNAVAILABLE"

    return DocumentJobProgressOut(
        document_id=doc.id,
        has_active_job=active is not None,  # CA-1
        active_job_id=active.id if active else None,
        step=active.step if active else None,  # CA-2
        action=action,
    )


@router.get("/{document_id}/fields", response_model=List[DocumentFieldOut])
async def get_document_fields(
    document_id: int, db: AsyncSession = Depends(get_db)
) -> List[DocumentFieldOut]:
    rows = (
        await db.execute(
            select(DocumentField)
            .where(DocumentField.document_id == document_id)
            .options(selectinload(DocumentField.field_spec))
        )
    ).scalars().all()
    return [
        DocumentFieldOut(
            id=df.id,
            document_id=df.document_id,
            field_spec_id=df.field_spec_id,
            group_id=df.group_id,
            value_type=df.field_spec.value_type if df.field_spec else None,
            ocr_value=df.ocr_value,
            resolved_value=df.resolved_value,
            status=df.status,
            ocr_confidence=df.ocr_confidence,
            consensus_reached=df.consensus_reached,
            ocr_polygon=df.ocr_polygon,
        )
        for df in rows
    ]


@router.get("/{document_id}/fields/by-section", response_model=DocumentFieldsBySectionOut)
async def get_document_fields_by_section(
    document_id: int, db: AsyncSession = Depends(get_db)
) -> DocumentFieldsBySectionOut:
    result = await db.execute(
        select(DocumentField)
        .where(DocumentField.document_id == document_id)
        .options(selectinload(DocumentField.field_spec))
    )
    sections: Dict[str, List[FieldBySectionItemOut]] = {}
    for df in result.scalars().all():
        sec = df.field_spec.section_id if df.field_spec else "unknown"
        sections.setdefault(sec, []).append(
            FieldBySectionItemOut(
                id=df.id,
                field_key=df.field_spec.field_key if df.field_spec else None,
            )
        )
    return DocumentFieldsBySectionOut(document_id=document_id, sections=sections)


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
    # CA-2 : recharger avec le fichier pour peupler page_count
    await db.refresh(doc, ["file"])
    return doc


@router.patch("/{document_id}", response_model=DocumentOut)
async def patch_document(
    document_id: int, body: DocumentPatch, db: AsyncSession = Depends(get_db)
) -> Document:
    result = await db.execute(
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.file))
    )
    doc = result.scalar_one_or_none()
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
