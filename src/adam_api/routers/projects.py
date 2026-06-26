"""Projects - scope de travail pour datasets."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.db import get_db
from adam_core.enums.roles import UserRole
from adam_core.models import Project, UserProject
from adam_core.utils.exceptions import raise_not_found

router = APIRouter(prefix="/projects", tags=["Projects"])


class ProjectIn(BaseModel):
    organisation_id: int
    name: str
    description: Optional[str] = None


class ProjectPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class UserProjectIn(BaseModel):
    user_id: int
    role: str = UserRole.OPERATOR.value


@router.get("", response_model=List[Dict[str, Any]])
async def list_projects(
    organisation_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    query = select(Project)
    if organisation_id is not None:
        query = query.where(Project.organisation_id == organisation_id)
    rows = (await db.execute(query)).scalars().all()
    return [{"id": r.id, "name": r.name, "organisation_id": r.organisation_id} for r in rows]


@router.get("/{project_id}", response_model=Dict[str, Any])
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    row = await db.get(Project, project_id)
    if not row:
        raise_not_found(Project)
    return {"id": row.id, "name": row.name, "status": row.status}


@router.post("", response_model=Dict[str, Any], status_code=201)
async def create_project(body: ProjectIn, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    row = Project(**body.model_dump())
    db.add(row)
    await db.flush()
    return {"id": row.id, "name": row.name}


@router.post("/{project_id}/users", response_model=Dict[str, Any], status_code=201)
async def add_user_to_project(
    project_id: int, body: UserProjectIn, db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    if not await db.get(Project, project_id):
        raise_not_found(Project)
    up = UserProject(user_id=body.user_id, project_id=project_id, role=body.role)
    db.add(up)
    await db.flush()
    return {"user_id": body.user_id, "project_id": project_id, "role": body.role}


@router.patch("/{project_id}", response_model=Dict[str, Any])
async def patch_project(
    project_id: int, body: ProjectPatch, db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    row = await db.get(Project, project_id)
    if not row:
        raise_not_found(Project)
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(row, key, val)
    await db.flush()
    return {"id": row.id, "name": row.name}


@router.delete("/{project_id}/users/{user_id}", status_code=204)
async def remove_user_from_project(
    project_id: int, user_id: int, db: AsyncSession = Depends(get_db)
) -> None:
    up = await db.get(UserProject, {"user_id": user_id, "project_id": project_id})
    if not up:
        raise_not_found(UserProject)
    await db.delete(up)
