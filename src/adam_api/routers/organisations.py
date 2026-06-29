"""Organisations - CRUD + archive/restore."""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.db import get_db
from adam_core.models import Organisation, User
from adam_core.schemas.responses import (
    OrgUserOut,
    OrganisationArchiveOut,
    OrganisationOut,
    OrganisationPatchOut,
)
from adam_core.utils.exceptions import raise_already_archived, raise_not_archived, raise_not_found

router = APIRouter(prefix="/organisations", tags=["Organisations"])


class OrganisationIn(BaseModel):
    name: str
    slug: str = Field(pattern=r"^[a-z0-9\-]+$")


class OrganisationPatch(BaseModel):
    name: Optional[str] = None


@router.get("", response_model=List[OrganisationOut])
async def list_organisations(db: AsyncSession = Depends(get_db)) -> List[OrganisationOut]:
    rows = (await db.execute(select(Organisation).where(Organisation.deleted_at.is_(None)))).scalars().all()
    return [OrganisationOut(id=r.id, name=r.name, slug=r.slug) for r in rows]


@router.get("/{org_id}/users", response_model=List[OrgUserOut])
async def list_org_users(org_id: int, db: AsyncSession = Depends(get_db)) -> List[OrgUserOut]:
    rows = (await db.execute(select(User).where(User.organisation_id == org_id))).scalars().all()
    return [OrgUserOut(id=r.id, email=r.email, matricule=r.matricule) for r in rows]


@router.post("", response_model=OrganisationOut, status_code=201)
async def create_organisation(body: OrganisationIn, db: AsyncSession = Depends(get_db)) -> OrganisationOut:
    row = Organisation(name=body.name, slug=body.slug)
    db.add(row)
    await db.flush()
    return OrganisationOut(id=row.id, name=row.name, slug=row.slug)


@router.patch("/{org_id}", response_model=OrganisationPatchOut)
async def patch_organisation(
    org_id: int, body: OrganisationPatch, db: AsyncSession = Depends(get_db)
) -> OrganisationPatchOut:
    row = await db.get(Organisation, org_id)
    if not row:
        raise_not_found(Organisation)
    if body.name is not None:
        row.name = body.name
    await db.flush()
    return OrganisationPatchOut(id=row.id, name=row.name)


@router.post("/{org_id}/archive", response_model=OrganisationArchiveOut)
async def archive_organisation(org_id: int, db: AsyncSession = Depends(get_db)) -> OrganisationArchiveOut:
    row = await db.get(Organisation, org_id)
    if not row:
        raise_not_found(Organisation)
    if row.deleted_at:
        raise_already_archived(Organisation)
    row.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    return OrganisationArchiveOut(id=row.id, archived=True)


@router.post("/{org_id}/restore", response_model=OrganisationArchiveOut)
async def restore_organisation(org_id: int, db: AsyncSession = Depends(get_db)) -> OrganisationArchiveOut:
    row = await db.get(Organisation, org_id)
    if not row:
        raise_not_found(Organisation)
    if not row.deleted_at:
        raise_not_archived(Organisation)
    row.deleted_at = None
    await db.flush()
    return OrganisationArchiveOut(id=row.id, archived=False)
