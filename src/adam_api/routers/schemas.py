"""Doc schemas and field specs."""

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from adam_api.dependencies.db import get_db
from adam_core.models import DocSchema, FieldSpec
from adam_core.schemas.responses import (
    FieldSpecItemOut,
    SchemaCreatedOut,
    SchemaDetailOut,
    SchemaListItemOut,
)
from adam_core.utils.exceptions import raise_not_found

router = APIRouter(prefix="/schemas", tags=["Schemas"])


class SchemaIn(BaseModel):
    project_id: int
    name: str
    document_type: str
    version: int = 1


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
        select(DocSchema).where(DocSchema.id == schema_id).options(selectinload(DocSchema.field_specs))
    )
    row = result.scalar_one_or_none()
    if not row:
        raise_not_found(DocSchema)
    return SchemaDetailOut(
        id=row.id,
        name=row.name,
        field_specs=[FieldSpecItemOut(id=fs.id, field_key=fs.field_key) for fs in row.field_specs],
    )


@router.post("", response_model=SchemaCreatedOut, status_code=201)
async def create_schema(body: SchemaIn, db: AsyncSession = Depends(get_db)) -> SchemaCreatedOut:
    row = DocSchema(**body.model_dump())
    db.add(row)
    await db.flush()
    return SchemaCreatedOut(id=row.id, name=row.name)
