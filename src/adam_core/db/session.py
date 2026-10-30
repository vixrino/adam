"""Engine SQLAlchemy async et session factory pour NOTA."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy import text
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from adam_core.db.scoping import (  # enregistre le listener do_orm_execute
    SESSION_MATRICULE_KEY,
    SESSION_ORG_KEY,
)
from adam_core.utils.logging import get_logger

logger = get_logger(__name__)

_engine = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

#: Delai accorde a la premiere connexion : au-dela, la base est consideree injoignable.
CONNECT_TIMEOUT_SECONDS = 5.0


class DatabaseUnavailable(RuntimeError):
    """La base n'a pas pu etre configuree ou jointe. Le message ne porte jamais de secret."""


def init_engine(database_url: str, *, echo: bool = False) -> None:
    global _engine, _async_session_factory
    logger.info("DB -> %s", database_url.split("@")[-1])
    try:
        _engine = create_async_engine(database_url, echo=echo, pool_pre_ping=True)
    except ArgumentError:
        # Le message de SQLAlchemy cite l'URL entiere, mot de passe compris : on ne le propage pas.
        raise DatabaseUnavailable(
            "URL de base de donnees invalide : verifier les variables POSTGRES_*"
        ) from None
    except ImportError as exc:
        raise DatabaseUnavailable(f"Pilote de base de donnees introuvable : {exc.name}") from exc
    _async_session_factory = async_sessionmaker(
        bind=_engine, class_=AsyncSession, expire_on_commit=False
    )


async def check_database(timeout: float = CONNECT_TIMEOUT_SECONDS) -> None:
    """Ouvre une connexion et lance `SELECT 1`. Leve DatabaseUnavailable si la base ne repond pas.

    create_async_engine est paresseux : sans cet appel, une base arretee ou un mauvais
    mot de passe n'apparaissent qu'a la premiere requete. Le message ne donne que
    l'hote, la base et le type de l'erreur : le texte de l'exception peut citer l'URL.
    """
    engine = get_engine()
    try:
        async with asyncio.timeout(timeout):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
    # Exception large a dessein : un mauvais mot de passe sort de asyncpg tel quel
    # (InvalidPasswordError, ni SQLAlchemyError ni OSError), et tout echec de cette
    # sonde veut dire la meme chose : la base n'est pas utilisable.
    except Exception as exc:  # pylint: disable=broad-exception-caught
        cause = getattr(exc, "orig", None) or exc
        raise DatabaseUnavailable(
            f"Base injoignable ({engine.url.render_as_string(hide_password=True)}) : "
            f"{type(cause).__name__}"
        ) from None


async def ensure_database() -> None:
    """Verifie la base au demarrage ; en cas d'echec, journalise et arrete le processus (code 1)."""
    try:
        await check_database()
    except DatabaseUnavailable as exc:
        logger.critical("%s", exc)
        raise SystemExit(1) from None


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Appelez init_engine() d'abord.")
    return _engine


async def create_tables() -> None:
    from adam_core.db.base import SCHEMA_NAME, Base

    async with get_engine().begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA_NAME}"'))
        await conn.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def get_async_session(
    organisation_id: Optional[int] = None,
    matricule: Optional[str] = None,
) -> AsyncIterator[AsyncSession]:
    """Ouvre une session ORM, optionnellement scopee a une organisation."""
    if _async_session_factory is None:
        raise RuntimeError("Session factory non initialisee.")
    async with _async_session_factory() as session:
        if organisation_id is not None:
            session.info[SESSION_ORG_KEY] = organisation_id
        if matricule is not None:
            session.info[SESSION_MATRICULE_KEY] = matricule
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
