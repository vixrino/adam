"""Schemas
GET : lecture simple et des field_specs
POST : creation d'un schema avec ses field_specs, ajout de field_specs, duplication versionnee
PATCH : mise a jour des field_specs
DELETE : suppression d'un field_spec avant le lock du schema
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.sql.functions import count
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from adam_api.dependencies.db import get_db
from adam_core.enums.status import DatasetStatus, FieldValueType
from adam_core.models import Dataset, DocSchema, DocumentField, FieldSpec
from adam_core.schemas.responses import (
    FieldSpecCreatedOut,
    FieldSpecDetailOut,
    FieldSpecItemOut,
    SchemaCreatedOut,
    SchemaDetailOut,
    SchemaListItemOut,
)
from adam_core.utils.exceptions import raise_conflict, raise_not_found

router = APIRouter(prefix="/schemas", tags=["Schemas"])


class FieldSpecIn(BaseModel):
    page: int
    section_id: str
    section_label: str
    field_key: str = Field(pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")
    display_label: str
    value_type: str = FieldValueType.TEXT.value
    required: bool = False
    display_order: int = 0
    group_id: Optional[str] = None
    polygon: Optional[List[float]] = Field(default=None, min_length=8, max_length=8)


class FieldSpecPatch(BaseModel):
    section_label: Optional[str] = None
    display_label: Optional[str] = None
    required: Optional[bool] = None
    display_order: Optional[int] = None
    polygon: Optional[List[float]] = Field(default=None, min_length=8, max_length=8)


class SchemaIn(BaseModel):
    project_id: int
    name: str
    document_type: str
    version: int = 1
    field_specs: List[FieldSpecIn] = Field(default_factory=list)


async def _check_schema_not_locked(schema_id: int, db: AsyncSession) -> None:
    """Leve 423 si le schema est utilise par un dataset non-brouillon."""
    active_dataset = (
        await db.execute(
            select(Dataset)
            .where(Dataset.schema_id == schema_id)
            .where(Dataset.status != DatasetStatus.DRAFT.value)
        )
    ).scalar_one_or_none()
    if active_dataset:
        raise HTTPException(
            status_code=423,
            detail=(
                f"Schema verrouille : utilise par le dataset '{active_dataset.name}' "
                f"(status={active_dataset.status}). "
                "Creer une nouvelle version du schema."
            ),
        )


def _spec_item_out(fs: FieldSpec) -> FieldSpecItemOut:
    return FieldSpecItemOut(
        id=fs.id,
        page=fs.page,
        section_id=fs.section_id,
        section_label=fs.section_label,
        field_key=fs.field_key,
        display_label=fs.display_label,
        value_type=fs.value_type,
        required=fs.required,
        display_order=fs.display_order,
        group_id=fs.group_id,
        polygon=fs.polygon,
        updated_at=fs.updated_at,
    )


def _spec_detail_out(fs: FieldSpec) -> FieldSpecDetailOut:
    return FieldSpecDetailOut(
        id=fs.id,
        schema_id=fs.schema_id,
        page=fs.page,
        section_id=fs.section_id,
        section_label=fs.section_label,
        field_key=fs.field_key,
        display_label=fs.display_label,
        value_type=fs.value_type,
        required=fs.required,
        display_order=fs.display_order,
        group_id=fs.group_id,
        polygon=fs.polygon,
        updated_at=fs.updated_at,
    )


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------

@router.get("", response_model=List[SchemaListItemOut])
async def list_schemas(
    project_id: Optional[int] = None, db: AsyncSession = Depends(get_db)
) -> List[SchemaListItemOut]:
    query = select(DocSchema)
    if project_id is not None:
        query = query.where(DocSchema.project_id == project_id)
    rows = (await db.execute(query)).scalars().all()
    return [
        SchemaListItemOut(
            id=r.id,
            name=r.name,
            document_type=r.document_type,
            version=r.version,
            project_id=r.project_id,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/field-specs/{field_spec_id}", response_model=FieldSpecDetailOut)
async def get_field_spec(
    field_spec_id: int, db: AsyncSession = Depends(get_db)
) -> FieldSpecDetailOut:
    """Detail d'un FieldSpec — utile pour le service OCR et l'IHM de creation de schema."""
    fs = await db.get(FieldSpec, field_spec_id)
    if not fs:
        raise_not_found(FieldSpec)
    return _spec_detail_out(fs)


@router.get("/{schema_id}", response_model=SchemaDetailOut)
async def get_schema(schema_id: int, db: AsyncSession = Depends(get_db)) -> SchemaDetailOut:
    result = await db.execute(
        select(DocSchema)
        .where(DocSchema.id == schema_id)
        .options(selectinload(DocSchema.field_specs))
    )
    schema = result.scalar_one_or_none()
    if not schema:
        raise_not_found(DocSchema)
    return SchemaDetailOut(
        id=schema.id,
        name=schema.name,
        document_type=schema.document_type,
        version=schema.version,
        project_id=schema.project_id,
        created_at=schema.created_at,
        updated_at=schema.updated_at,
        field_specs=[
            _spec_item_out(fs)
            for fs in sorted(schema.field_specs, key=lambda x: (x.page, x.display_order))
        ],
    )


# ---------------------------------------------------------------------------
# POST
# ---------------------------------------------------------------------------

@router.post("", response_model=SchemaCreatedOut, status_code=201)
async def create_schema(payload: SchemaIn, db: AsyncSession = Depends(get_db)) -> SchemaCreatedOut:
    """Cree un schema avec ses field_specs en une seule transaction."""
    schema = DocSchema(
        project_id=payload.project_id,
        name=payload.name,
        document_type=payload.document_type,
        version=payload.version,
    )
    db.add(schema)
    await db.flush()

    field_specs = [
        FieldSpec(
            schema_id=schema.id,
            page=fs_in.page,
            section_id=fs_in.section_id,
            section_label=fs_in.section_label,
            field_key=fs_in.field_key,
            display_label=fs_in.display_label,
            value_type=fs_in.value_type,
            required=fs_in.required,
            display_order=fs_in.display_order,
            group_id=fs_in.group_id,
            polygon=fs_in.polygon,
        )
        for fs_in in payload.field_specs
    ]
    db.add_all(field_specs)
    await db.flush()

    return SchemaCreatedOut(
        id=schema.id,
        name=schema.name,
        document_type=schema.document_type,
        version=schema.version,
        field_specs_created=len(field_specs),
    )


@router.post("/{schema_id}/field-specs", response_model=FieldSpecCreatedOut, status_code=201)
async def add_field_spec(
    schema_id: int, payload: FieldSpecIn, db: AsyncSession = Depends(get_db)
) -> FieldSpecCreatedOut:
    """Ajoute un champ a un schema existant. Interdit si le schema est verrouille."""
    await _check_schema_not_locked(schema_id, db)
    schema = await db.get(DocSchema, schema_id)
    if not schema:
        raise_not_found(DocSchema)
    fs = FieldSpec(
        schema_id=schema_id,
        page=payload.page,
        section_id=payload.section_id,
        section_label=payload.section_label,
        field_key=payload.field_key,
        display_label=payload.display_label,
        value_type=payload.value_type,
        required=payload.required,
        display_order=payload.display_order,
        group_id=payload.group_id,
        polygon=payload.polygon,
    )
    db.add(fs)
    await db.flush()
    return FieldSpecCreatedOut(id=fs.id, field_key=fs.field_key, schema_id=schema_id)


@router.post("/{schema_id}/duplicate", response_model=SchemaCreatedOut, status_code=201)
async def duplicate_schema(
    schema_id: int, db: AsyncSession = Depends(get_db)
) -> SchemaCreatedOut:
    """Duplique un schema avec tous ses FieldSpecs en incrementant la version.
    Utile pour modifier un schema deja utilise sans casser l'historique."""
    result = await db.execute(
        select(DocSchema)
        .where(DocSchema.id == schema_id)
        .options(selectinload(DocSchema.field_specs))
    )
    source = result.scalar_one_or_none()
    if not source:
        raise_not_found(DocSchema)

    latest_version = (
        await db.execute(
            select(func.max(DocSchema.version))
            .where(DocSchema.project_id == source.project_id)
            .where(DocSchema.document_type == source.document_type)
        )
    ).scalar_one()

    new_schema = DocSchema(
        project_id=source.project_id,
        name=source.name,
        document_type=source.document_type,
        version=(latest_version or 0) + 1,
    )
    db.add(new_schema)
    await db.flush()

    new_specs = [
        FieldSpec(
            schema_id=new_schema.id,
            page=fs.page,
            section_id=fs.section_id,
            section_label=fs.section_label,
            field_key=fs.field_key,
            display_label=fs.display_label,
            value_type=fs.value_type,
            required=fs.required,
            display_order=fs.display_order,
            group_id=fs.group_id,
            polygon=fs.polygon,
        )
        for fs in source.field_specs
    ]
    db.add_all(new_specs)
    await db.flush()

    return SchemaCreatedOut(
        id=new_schema.id,
        name=new_schema.name,
        document_type=new_schema.document_type,
        version=new_schema.version,
        field_specs_created=len(new_specs),
    )


# ---------------------------------------------------------------------------
# PATCH
# ---------------------------------------------------------------------------

@router.patch("/{schema_id}/field-specs/{spec_id}", response_model=FieldSpecItemOut)
async def patch_field_spec(
    schema_id: int, spec_id: int, body: FieldSpecPatch, db: AsyncSession = Depends(get_db)
) -> FieldSpecItemOut:
    await _check_schema_not_locked(schema_id, db)
    fs = await db.get(FieldSpec, spec_id)
    if not fs or fs.schema_id != schema_id:
        raise_not_found(FieldSpec)
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(fs, key, val)
    await db.flush()
    return _spec_item_out(fs)


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@router.delete("/{schema_id}/field-specs/{spec_id}", status_code=204)
async def delete_field_spec(
    schema_id: int, spec_id: int, db: AsyncSession = Depends(get_db)
) -> None:
    """Supprime un field_spec. Interdit si le schema est verrouille par un dataset actif."""
    await _check_schema_not_locked(schema_id, db)
    fs = await db.get(FieldSpec, spec_id)
    if not fs or fs.schema_id != schema_id:
        raise_not_found(FieldSpec)
    referenced: int = (
        await db.execute(
            select(count(DocumentField.id)).where(DocumentField.field_spec_id == spec_id)
        )
    ).scalar_one()
    if referenced:
        raise_conflict(FieldSpec, f"FieldSpec {spec_id} est reference par {referenced} document(s)")
    await db.delete(fs)
