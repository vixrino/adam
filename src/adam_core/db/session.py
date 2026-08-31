"""Engine SQLAlchemy async et session factory pour ADAM."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from adam_core.db.scoping import SESSION_ORG_KEY  # enregistre le listener do_orm_execute
from adam_core.utils.logging import get_logger

logger = get_logger(__name__)

_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def init_engine(database_url: str, *, echo: bool = False) -> None:
    global _engine, _async_session_factory
    logger.info("DB -> %s", database_url.split("@")[-1])
    _engine = create_async_engine(database_url, echo=echo, pool_pre_ping=True)
    _async_session_factory = async_sessionmaker(
        bind=_engine, class_=AsyncSession, expire_on_commit=False
    )


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Appelez init_engine() d'abord.")
    return _engine


async def create_tables() -> None:
    from adam_core.db.base import Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_async_session(
    organisation_id: Optional[int] = None,
) -> AsyncIterator[AsyncSession]:
    """Ouvre une session ORM, optionnellement scopee a une organisation.

    Quand ``organisation_id`` est fourni (contexte utilisateur resolu via le
    caller), il est pose en ``session.info`` avant le yield : le listener
    global ``do_orm_execute`` filtre alors automatiquement toutes les tables
    ``OrganisationScoped``. Sans organisation_id (services machine, workers,
    taches de fond), aucun filtre n'est applique.
    """
    if _async_session_factory is None:
        raise RuntimeError("Session factory non initialisee.")
    async with _async_session_factory() as session:
        if organisation_id is not None:
            session.info[SESSION_ORG_KEY] = organisation_id
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
