"""Schemas
GET : lecture simple et des field_specs
POST : creation d'un schema et des field_specs
PATCH : mise a jour des field_specs
DELETE : suppression d'un field_spec avant le lock du schema
"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from adam_api.dependencies.db import get_db
from adam_core.enums.status import DatasetStatus, FieldValueType
from adam_core.models import Dataset, DocSchema, FieldSpec
from adam_core.schemas.responses import (
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
    display_label: Optional[str] = None
    value_type: Optional[str] = None
    required: Optional[bool] = None
    display_order: Optional[int] = None
    polygon: Optional[List[float]] = Field(default=None, min_length=8, max_length=8)


class SchemaIn(BaseModel):
    project_id: int
    name: str
    document_type: str
    version: int = 1


def _spec_out(fs: FieldSpec) -> FieldSpecItemOut:
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


@router.get("", response_model=List[SchemaListItemOut])
async def list_schemas(
    project_id: Optional[int] = None, db: AsyncSession = Depends(get_db)
) -> List[SchemaListItemOut]:
    query = select(DocSchema)
    if project_id is not None:
        query = query.where(DocSchema.project_id == project_id)
    rows = (await db.execute(query)).scalars().all()
    return [SchemaListItemOut(id=r.id, name=r.name, document_type=r.document_type) for r in rows]


@router.get("/{schema_id}", response_model=SchemaDetailOut)
async def get_schema(schema_id: int, db: AsyncSession = Depends(get_db)) -> SchemaDetailOut:
    result = await db.execute(
        select(DocSchema)
        .where(DocSchema.id == schema_id)
        .options(selectinload(DocSchema.field_specs))
    )
    row = result.scalar_one_or_none()
    if not row:
        raise_not_found(DocSchema)
    return SchemaDetailOut(
        id=row.id,
        name=row.name,
        document_type=row.document_type,
        version=row.version,
        project_id=row.project_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        field_specs=[_spec_out(fs) for fs in sorted(row.field_specs, key=lambda s: (s.page, s.display_order))],
    )


@router.post("", response_model=SchemaCreatedOut, status_code=201)
async def create_schema(body: SchemaIn, db: AsyncSession = Depends(get_db)) -> SchemaCreatedOut:
    row = DocSchema(**body.model_dump())
    db.add(row)
    await db.flush()
    return SchemaCreatedOut(id=row.id, name=row.name, document_type=row.document_type)


@router.post("/{schema_id}/field-specs", response_model=FieldSpecItemOut, status_code=201)
async def create_field_spec(
    schema_id: int, body: FieldSpecIn, db: AsyncSession = Depends(get_db)
) -> FieldSpecItemOut:
    schema = await db.get(DocSchema, schema_id)
    if not schema:
        raise_not_found(DocSchema)
    existing = (
        await db.execute(
            select(FieldSpec)
            .where(FieldSpec.schema_id == schema_id)
            .where(FieldSpec.section_id == body.section_id)
            .where(FieldSpec.field_key == body.field_key)
            .where(FieldSpec.group_id == body.group_id)
        )
    ).scalar_one_or_none()
    if existing:
        raise_conflict(FieldSpec, f"field_key '{body.field_key}' deja present dans la section '{body.section_id}'")
    fs = FieldSpec(schema_id=schema_id, **body.model_dump())
    db.add(fs)
    await db.flush()
    return _spec_out(fs)


@router.patch("/{schema_id}/field-specs/{spec_id}", response_model=FieldSpecItemOut)
async def patch_field_spec(
    schema_id: int, spec_id: int, body: FieldSpecPatch, db: AsyncSession = Depends(get_db)
) -> FieldSpecItemOut:
    fs = await db.get(FieldSpec, spec_id)
    if not fs or fs.schema_id != schema_id:
        raise_not_found(FieldSpec)
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(fs, key, val)
    await db.flush()
    return _spec_out(fs)


@router.delete("/{schema_id}/field-specs/{spec_id}", status_code=204)
async def delete_field_spec(
    schema_id: int, spec_id: int, db: AsyncSession = Depends(get_db)
) -> None:
    """Supprime un field_spec. Interdit si le schema est utilise par un dataset actif."""
    fs = await db.get(FieldSpec, spec_id)
    if not fs or fs.schema_id != schema_id:
        raise_not_found(FieldSpec)
    locked = (
        await db.execute(
            select(func.count(Dataset.id))
            .where(Dataset.schema_id == schema_id)
            .where(Dataset.status != DatasetStatus.DRAFT.value)
        )
    ).scalar_one()
    if locked:
        raise_conflict(DocSchema, "Schema verrouille : des datasets actifs utilisent ce schema")
    await db.delete(fs)
