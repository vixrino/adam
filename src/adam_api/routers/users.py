"""Users
GET : lecture avec filtres
POST : creation d'un utilisateur
PATCH : mise a jour de nom et status, ainsi que l'archivage (soft delete) et restauration
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from adam_api.dependencies.db import get_db
from adam_core.enums.status import UserStatus
from adam_core.models import User
from adam_core.schemas.responses import (
    UserCreatedOut,
    UserDetailOut,
    UserListItemOut,
    UserPatchOut,
    UserProjectDetailOut,
)
from adam_core.utils.exceptions import (
    raise_already_archived,
    raise_conflict,
    raise_not_archived,
    raise_not_found,
    raise_unprocessable,
)

router = APIRouter(prefix="/users", tags=["Users"])


class UserIn(BaseModel):
    organisation_id: int
    email: str
    full_name: str
    matricule: str


class UserPatch(BaseModel):
    full_name: Optional[str] = None
    status: Optional[str] = None


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------

@router.get("", response_model=List[UserListItemOut])
async def list_users(
    include_deleted: bool = False,
    organisation_id: Optional[int] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> List[UserListItemOut]:
    query = select(User)
    if not include_deleted:
        query = query.where(User.deleted_at.is_(None))
    if organisation_id:
        query = query.where(User.organisation_id == organisation_id)
    if status:
        query = query.where(User.status == status)
    rows = (await db.execute(query)).scalars().all()
    return [
        UserListItemOut(
            id=r.id,
            email=r.email,
            full_name=r.full_name,
            matricule=r.matricule,
            status=r.status,
            organisation_id=r.organisation_id,
            created_at=r.created_at,
            updated_at=r.updated_at,
            deleted_at=r.deleted_at,
        )
        for r in rows
    ]


@router.get("/{user_id}", response_model=UserDetailOut)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)) -> UserDetailOut:
    result = await db.execute(
        select(User).where(User.id == user_id).options(selectinload(User.user_projects))
    )
    user = result.scalar_one_or_none()
    if not user:
        raise_not_found(User)
    return UserDetailOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        matricule=user.matricule,
        status=user.status,
        organisation_id=user.organisation_id,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        updated_at=user.updated_at,
        deleted_at=user.deleted_at,
        projects=[
            UserProjectDetailOut(
                project_id=up.project_id,
                role=up.role,
                created_at=up.created_at,
            )
            for up in user.user_projects
        ],
    )


# ---------------------------------------------------------------------------
# POST
# ---------------------------------------------------------------------------

@router.post("", response_model=UserCreatedOut, status_code=201)
async def create_user(payload: UserIn, db: AsyncSession = Depends(get_db)) -> UserCreatedOut:
    existing_email = (
        await db.execute(select(User).where(User.email == payload.email))
    ).scalar_one_or_none()
    if existing_email:
        raise_conflict(User, f"email '{payload.email}' deja utilise")

    existing_mat = (
        await db.execute(select(User).where(User.matricule == payload.matricule))
    ).scalar_one_or_none()
    if existing_mat:
        raise_conflict(User, f"Matricule '{payload.matricule}' deja utilise")

    user = User(
        organisation_id=payload.organisation_id,
        email=payload.email,
        full_name=payload.full_name,
        matricule=payload.matricule,
        status=UserStatus.ACTIVE.value,
    )
    db.add(user)
    await db.flush()
    return UserCreatedOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        matricule=user.matricule,
        status=user.status,
    )


# ---------------------------------------------------------------------------
# PATCH
# ---------------------------------------------------------------------------

@router.patch("/{user_id}", response_model=UserPatchOut)
async def patch_user(
    user_id: int,
    payload: UserPatch,
    db: AsyncSession = Depends(get_db),
) -> UserPatchOut:
    user = await db.get(User, user_id)
    if not user:
        raise_not_found(User)
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.status is not None:
        allowed = [str(s.value) for s in UserStatus]
        if payload.status not in allowed:
            raise_unprocessable(f"Statut invalide. Valeurs acceptees : {allowed}")
        user.status = payload.status
    await db.flush()
    return UserPatchOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        matricule=user.matricule,
        status=user.status,
        organisation_id=user.organisation_id,
        created_at=user.created_at,
        updated_at=user.updated_at,
        deleted_at=user.deleted_at,
    )


# ---------------------------------------------------------------------------
# Archive / Restore
# ---------------------------------------------------------------------------

@router.post("/{user_id}/archive", response_model=UserPatchOut)
async def archive_user(user_id: int, db: AsyncSession = Depends(get_db)) -> UserPatchOut:
    user = await db.get(User, user_id)
    if not user:
        raise_not_found(User)
    if user.deleted_at is not None:
        raise_already_archived(User)
    user.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    return UserPatchOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        matricule=user.matricule,
        status=user.status,
        organisation_id=user.organisation_id,
        created_at=user.created_at,
        updated_at=user.updated_at,
        deleted_at=user.deleted_at,
    )


@router.post("/{user_id}/restore", response_model=UserPatchOut)
async def restore_user(user_id: int, db: AsyncSession = Depends(get_db)) -> UserPatchOut:
    user = await db.get(User, user_id)
    if not user:
        raise_not_found(User)
    if user.deleted_at is None:
        raise_not_archived(User)
    user.deleted_at = None
    await db.flush()
    return UserPatchOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        matricule=user.matricule,
        status=user.status,
        organisation_id=user.organisation_id,
        created_at=user.created_at,
        updated_at=user.updated_at,
        deleted_at=user.deleted_at,
    )
