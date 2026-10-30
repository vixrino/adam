"""Droits sur un projet : qui peut le modifier et gerer ses membres."""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.auth import UserCaller
from adam_core.enums.roles import CROSS_ORGANISATION_ROLE_VALUES, ProjectRole
from adam_core.models import Project, User, UserProject
from adam_core.utils.exceptions import raise_not_found


async def verifier_admin_projet(db: AsyncSession, caller: UserCaller, project_id: int) -> Project:
    """Projet vise, si l'appelant peut le gerer ; 404 / 403 sinon.

    Peuvent le gerer : les roles de plateforme transverses (Administrateur et
    Superviseur NOTA) partout, et un administrateur metier (BUSINESS_ADMIN) sur
    les projets ou il est inscrit comme tel. Un operateur peut lire, pas gerer.
    """
    project = await db.get(Project, project_id)
    if project is None:
        raise_not_found(Project)
    if caller.platform_role in CROSS_ORGANISATION_ROLE_VALUES:
        return project
    est_admin_metier = (
        await db.execute(
            select(UserProject.user_id)
            .join(User, User.id == UserProject.user_id)
            .where(func.upper(User.matricule) == caller.matricule.upper())
            .where(UserProject.project_id == project_id)
            .where(UserProject.role == ProjectRole.BUSINESS_ADMIN.value)
        )
    ).first()
    if est_admin_metier is None:
        raise HTTPException(
            status_code=403,
            detail="Reserve aux administrateurs NOTA et aux administrateurs metier du projet",
        )
    return project
