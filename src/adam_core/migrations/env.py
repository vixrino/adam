import asyncio
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Path setup
_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "src"))

from adam_core.core.config import CoreSettings
from adam_core.db.base import SCHEMA_NAME, Base
import adam_core.models  # noqa: F401
from adam_core.utils.logging import get_logger, setup_logging

_settings = CoreSettings()

setup_logging(_settings)
logger = get_logger(__name__)

# Config Alembic
config = context.config

target_metadata = Base.metadata


def include_name(name: str | None, type_: str, _parent_names: object) -> bool:
    """Base partagee : ne regarder que notre schema, jamais les tables des autres applications."""
    return name == SCHEMA_NAME if type_ == "schema" else True


# La base est partagee et nos tables vivent dans SCHEMA_NAME, y compris la table de versions.
_SCHEMA_OPTIONS = {
    "include_schemas": True,
    "include_name": include_name,
    "version_table_schema": SCHEMA_NAME,
}


def run_migrations_offline() -> None:
    sync_url = _settings.migration_database_url.replace("+asyncpg", "")
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        **_SCHEMA_OPTIONS,
    )
    with context.begin_transaction():
        # Pas de SET search_path : les migrations qualifient toutes `schema="nota"`. Avec lui,
        # Alembic prend nota pour le schema par defaut et `check` voit chaque table « nouvelle ».
        context.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA_NAME}"')
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        **_SCHEMA_OPTIONS,
    )
    with context.begin_transaction():
        # Pas de SET search_path : cf. run_migrations_offline.
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA_NAME}"'))
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(
        _settings.migration_database_url,
        poolclass=pool.NullPool,
        connect_args={"server_settings": {"search_path": "public"}},
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
