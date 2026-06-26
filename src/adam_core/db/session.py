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
async def get_async_session() -> AsyncIterator[AsyncSession]:
    if _async_session_factory is None:
        raise RuntimeError("Session factory non initialisee.")
    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
