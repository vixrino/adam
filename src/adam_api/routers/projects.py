"""Projects - scope de travail pour datasets."""

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.db import get_db
from adam_core.enums.roles import UserRole
from adam_core.enums.status import ProjectStatus
from adam_core.models import Project, UserProject
from adam_core.schemas.responses import (
    ProjectCreatedOut,
    ProjectDetailOut,
    ProjectOut,
    UserProjectOut,
    UserRolePatchOut,
)
from adam_core.utils.exceptions import raise_not_found, raise_unprocessable

router = APIRouter(prefix="/projects", tags=["Projects"])


class ProjectIn(BaseModel):
    organisation_id: int
    name: str
    description: Optional[str] = None


class ProjectPatch(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class UserProjectIn(BaseModel):
    user_id: int
    role: str = UserRole.OPERATOR.value


class UserRolePatch(BaseModel):
    role: str


@router.get("", response_model=List[ProjectOut])
async def list_projects(
    organisation_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
) -> List[ProjectOut]:
    query = select(Project)
    if organisation_id is not None:
        query = query.where(Project.organisation_id == organisation_id)
    rows = (await db.execute(query)).scalars().all()
    return [ProjectOut(id=r.id, name=r.name, organisation_id=r.organisation_id) for r in rows]


@router.get("/{project_id}", response_model=ProjectDetailOut)
async def get_project(project_id: int, db: AsyncSession = Depends(get_db)) -> ProjectDetailOut:
    row = await db.get(Project, project_id)
    if not row:
        raise_not_found(Project)
    return ProjectDetailOut(id=row.id, name=row.name, status=row.status, updated_at=row.updated_at)


@router.post("", response_model=ProjectCreatedOut, status_code=201)
async def create_project(body: ProjectIn, db: AsyncSession = Depends(get_db)) -> ProjectCreatedOut:
    row = Project(**body.model_dump())
    db.add(row)
    await db.flush()
    return ProjectCreatedOut(id=row.id, name=row.name)


@router.post("/{project_id}/users", response_model=UserProjectOut, status_code=201)
async def add_user_to_project(
    project_id: int, body: UserProjectIn, db: AsyncSession = Depends(get_db)
) -> UserProjectOut:
    if not await db.get(Project, project_id):
        raise_not_found(Project)
    up = UserProject(user_id=body.user_id, project_id=project_id, role=body.role)
    db.add(up)
    await db.flush()
    return UserProjectOut(user_id=up.user_id, project_id=project_id, role=up.role)


@router.patch("/{project_id}", response_model=ProjectDetailOut)
async def patch_project(
    project_id: int, body: ProjectPatch, db: AsyncSession = Depends(get_db)
) -> ProjectDetailOut:
    row = await db.get(Project, project_id)
    if not row:
        raise_not_found(Project)
    if body.name is not None:
        row.name = body.name
    if body.description is not None:
        row.description = body.description
    if body.status is not None:
        allowed = [s.value for s in ProjectStatus]
        if body.status not in allowed:
            raise_unprocessable(f"Statut invalide. Valeurs acceptees : {allowed}")
        row.status = body.status
    await db.flush()
    return ProjectDetailOut(id=row.id, name=row.name, status=row.status, updated_at=row.updated_at)


@router.patch("/{project_id}/users/{user_id}", response_model=UserRolePatchOut)
async def update_user_role(
    project_id: int, user_id: int, body: UserRolePatch, db: AsyncSession = Depends(get_db)
) -> UserRolePatchOut:
    """Change le role d'un utilisateur sur un projet."""
    up = (
        await db.execute(
            select(UserProject)
            .where(UserProject.project_id == project_id)
            .where(UserProject.user_id == user_id)
        )
    ).scalar_one_or_none()
    if not up:
        raise_not_found(UserProject, f"User {user_id} n'est pas assigne au projet {project_id}")
    allowed = [r.value for r in UserRole]
    if body.role not in allowed:
        raise_unprocessable(f"Role invalide. Valeurs acceptees : {allowed}")
    up.role = body.role
    return UserRolePatchOut(
        user_id=user_id,
        project_id=project_id,
        role=up.role,
        updated_at=up.updated_at,
    )


@router.delete("/{project_id}/users/{user_id}", status_code=204)
async def remove_user_from_project(
    project_id: int, user_id: int, db: AsyncSession = Depends(get_db)
) -> None:
    """Retire un utilisateur d'un projet. Pas de soft delete."""
    up = (
        await db.execute(
            select(UserProject)
            .where(UserProject.project_id == project_id)
            .where(UserProject.user_id == user_id)
        )
    ).scalar_one_or_none()
    if not up:
        raise_not_found(UserProject, f"User {user_id} n'est pas assigne au projet {project_id}")
    await db.delete(up)
