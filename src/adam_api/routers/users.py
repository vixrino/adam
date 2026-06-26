"""Users CRUD."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.db import get_db
from adam_core.enums.status import UserStatus
from adam_core.models import User
from adam_core.utils.exceptions import raise_not_found

router = APIRouter(prefix="/users", tags=["Users"])


class UserIn(BaseModel):
    organisation_id: int
    email: EmailStr
    full_name: str
    matricule: str


class UserPatch(BaseModel):
    full_name: Optional[str] = None
    status: Optional[str] = None


@router.get("", response_model=List[Dict[str, Any]])
async def list_users(
    organisation_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    query = select(User)
    if organisation_id is not None:
        query = query.where(User.organisation_id == organisation_id)
    rows = (await db.execute(query)).scalars().all()
    return [{"id": r.id, "email": r.email, "matricule": r.matricule} for r in rows]


@router.get("/{user_id}", response_model=Dict[str, Any])
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    row = await db.get(User, user_id)
    if not row:
        raise_not_found(User)
    return {"id": row.id, "email": row.email, "status": row.status}


@router.post("", response_model=Dict[str, Any], status_code=201)
async def create_user(body: UserIn, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    row = User(**body.model_dump(), status=UserStatus.ACTIVE.value)
    db.add(row)
    await db.flush()
    return {"id": row.id, "email": row.email}


@router.patch("/{user_id}", response_model=Dict[str, Any])
async def patch_user(user_id: int, body: UserPatch, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    row = await db.get(User, user_id)
    if not row:
        raise_not_found(User)
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(row, key, val)
    await db.flush()
    return {"id": row.id, "status": row.status}
