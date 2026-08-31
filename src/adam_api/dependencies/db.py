"""Dependency FastAPI pour l'injection de session SQLAlchemy.

La session depend du caller resolu : c'est le point d'entree du filtrage
multi-tenant. Un UserCaller pose son ``organisation_id`` en session (le
listener do_orm_execute filtre alors toutes les tables OrganisationScoped) ;
un ServiceCaller (service machine, worker) n'impose aucun filtre. Quand le
FBI sera branche, seul le contenu de get_caller changera, pas cette chaine.
"""

from collections.abc import AsyncGenerator
from typing import Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.dependencies.auth import Caller, UserCaller, get_caller
from adam_core.db.session import get_async_session


def _organisation_id_of(caller: Caller) -> Optional[int]:
    """Organisation a scoper, ou None pour un appelant non-utilisateur."""
    if isinstance(caller, UserCaller):
        return caller.organisation_id
    return None


async def get_db(
    caller: Caller = Depends(get_caller),
) -> AsyncGenerator[AsyncSession, None]:
    async with get_async_session(organisation_id=_organisation_id_of(caller)) as session:
        yield session
