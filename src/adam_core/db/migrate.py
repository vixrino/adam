"""Mise a niveau du schema par Alembic.

`upgrade_head()` est synchrone : l'env.py d'Alembic ouvre sa propre boucle asyncio, ce qui
echoue dans un contexte deja async (les scripts l'appellent donc via asyncio.to_thread).
Le verrou qui serialise des migrations concurrentes vit dans env.py, dans la transaction DDL.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config

from adam_core.utils.logging import get_logger

logger = get_logger(__name__)

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def alembic_config() -> Config:
    return Config(str(ALEMBIC_INI))


def upgrade_head() -> None:
    """Applique les migrations jusqu'a head ; en cas d'echec, journalise et arrete (code 1)."""
    try:
        command.upgrade(alembic_config(), "head")
    # Exception large a dessein : tout echec ici veut dire que le schema n'est pas utilisable.
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.critical("Migration impossible : %s : %s", type(exc).__name__, exc)
        raise SystemExit(1) from None
    logger.info("schema a jour")
