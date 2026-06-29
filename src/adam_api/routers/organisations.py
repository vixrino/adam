"""Organisations
GET : lecture simple
POST : creation d'une org, archivage et restauration
PATCH : mise a jour Org name
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from adam_api.dependencies.db import get_db
from adam_core.models import Organisation, User
from adam_core.schemas.responses import OrgUserOut, OrganisationOut, UserProjectRefOut
from adam_core.utils.exceptions import (
    raise_already_archived,
    raise_conflict,
    raise_not_archived,
    raise_not_found,
)

router = APIRouter(prefix="/organisations", tags=["Organisations"])


class OrganisationIn(BaseModel):
    name: str
    slug: str = Field(pattern=r"^[a-z0-9\-]+$")


class OrganisationPatch(BaseModel):
    name: Optional[str] = None


@router.get("", response_model=List[OrganisationOut])
async def list_organisations(
    include_deleted: bool = False,
    organisation_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
) -> List[OrganisationOut]:
    query = select(Organisation)
    if not include_deleted:
        query = query.where(Organisation.deleted_at.is_(None))
    if organisation_id:
        query = query.where(Organisation.id == organisation_id)
    rows = (await db.execute(query)).scalars().all()
    return [
        OrganisationOut(
            id=r.id,
            name=r.name,
            slug=r.slug,
            created_at=r.created_at,
            updated_at=r.updated_at,
            deleted_at=r.deleted_at,
        )
        for r in rows
    ]


@router.get("/{organisation_id}/users", response_model=List[OrgUserOut])
async def list_organisation_users(
    organisation_id: int,
    db: AsyncSession = Depends(get_db),
) -> List[OrgUserOut]:
    """Liste les utilisateurs d'une organisation."""
    org = await db.get(Organisation, organisation_id)
    if not org:
        raise_not_found(Organisation)
    if org.deleted_at is not None:
        raise_not_found(Organisation)

    rows = (
        (
            await db.execute(
                select(User)
                .where(User.organisation_id == organisation_id)
                .options(selectinload(User.user_projects))
            )
        )
        .scalars()
        .all()
    )

    return [
        OrgUserOut(
            id=r.id,
            email=r.email,
            full_name=r.full_name,
            matricule=r.matricule,
            status=r.status,
            projects=[UserProjectRefOut(project_id=up.project_id, role=up.role) for up in r.user_projects],
        )
        for r in rows
    ]


@router.post("", response_model=OrganisationOut, status_code=201)
async def create_organisation(
    payload: OrganisationIn, db: AsyncSession = Depends(get_db)
) -> OrganisationOut:
    existing = (
        await db.execute(select(Organisation).where(Organisation.slug == payload.slug))
    ).scalar_one_or_none()
    if existing:
        raise_conflict(Organisation, detail=f"Slug '{payload.slug}' deja utilise")

    org = Organisation(name=payload.name, slug=payload.slug)
    db.add(org)
    await db.flush()
    return OrganisationOut(
        id=org.id,
        name=org.name,
        slug=org.slug,
        created_at=org.created_at,
        updated_at=org.updated_at,
        deleted_at=org.deleted_at,
    )


@router.patch("/{organisation_id}", response_model=OrganisationOut)
async def patch_organisation(
    organisation_id: int,
    payload: OrganisationPatch,
    db: AsyncSession = Depends(get_db),
) -> OrganisationOut:
    org = await db.get(Organisation, organisation_id)
    if not org:
        raise_not_found(Organisation)
    if org.deleted_at is not None:
        raise_already_archived(Organisation)
    if payload.name is not None:
        org.name = payload.name
    return OrganisationOut(
        id=org.id,
        name=org.name,
        slug=org.slug,
        created_at=org.created_at,
        updated_at=org.updated_at,
        deleted_at=org.deleted_at,
    )


@router.post("/{organisation_id}/archive", response_model=OrganisationOut)
async def archive_organisation(
    organisation_id: int, db: AsyncSession = Depends(get_db)
) -> OrganisationOut:
    """Soft delete, masque l'organisation sans la supprimer."""
    org = await db.get(Organisation, organisation_id)
    if not org:
        raise_not_found(Organisation)
    if org.deleted_at is not None:
        raise_already_archived(Organisation)
    org.deleted_at = datetime.now(timezone.utc)
    return OrganisationOut(
        id=org.id,
        name=org.name,
        slug=org.slug,
        created_at=org.created_at,
        updated_at=org.updated_at,
        deleted_at=org.deleted_at,
    )


@router.post("/{organisation_id}/restore", response_model=OrganisationOut)
async def restore_organisation(
    organisation_id: int, db: AsyncSession = Depends(get_db)
) -> OrganisationOut:
    """Restaure une organisation archivee."""
    org = await db.get(Organisation, organisation_id)
    if not org:
        raise_not_found(Organisation)
    if org.deleted_at is None:
        raise_not_archived(Organisation)
    org.deleted_at = None
    return OrganisationOut(
        id=org.id,
        name=org.name,
        slug=org.slug,
        created_at=org.created_at,
        updated_at=org.updated_at,
        deleted_at=org.deleted_at,
    )
