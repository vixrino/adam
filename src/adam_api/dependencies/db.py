"""
Dependency FastAPI pour l'injection de session SQLAlchemy.
"""

from collections.abc import AsyncGenerator
from typing import Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.auth import (
    Caller,
    UserCaller,
    get_caller,
    get_caller_premiere_connexion,
)
from adam_core.db.session import get_async_session
from adam_core.enums.roles import CROSS_ORGANISATION_ROLE_VALUES


def _organisation_id_of(caller: Caller) -> Optional[int]:
    """Organisation a scoper, ou None quand aucun filtre ne doit s'appliquer."""
    if isinstance(caller, UserCaller):
        if caller.platform_role in CROSS_ORGANISATION_ROLE_VALUES:
            return None
        return caller.organisation_id
    return None


def _matricule_of(caller: Caller) -> Optional[str]:
    """Matricule a scoper par projet, ou None quand aucun filtre ne s'applique."""
    if isinstance(caller, UserCaller):
        if caller.platform_role in CROSS_ORGANISATION_ROLE_VALUES:
            return None
        return caller.matricule
    return None


async def get_db(
    caller: Caller = Depends(get_caller),
) -> AsyncGenerator[AsyncSession, None]:
    async with get_async_session(
        organisation_id=_organisation_id_of(caller),
        matricule=_matricule_of(caller),
    ) as session:
        yield session


async def get_db_premiere_connexion(
    caller: Caller = Depends(get_caller_premiere_connexion),
) -> AsyncGenerator[AsyncSession, None]:
    """Session de GET /users/me : meme scope que get_db, mais derive du caller
    qui cree la ligne `user` a la premiere connexion. get_db, lui, resoudrait le
    caller par get_caller et refuserait l'agent avant sa creation."""
    async with get_async_session(
        organisation_id=_organisation_id_of(caller),
        matricule=_matricule_of(caller),
    ) as session:
        yield session
