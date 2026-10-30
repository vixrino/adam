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
    sync_url = _settings.async_database_url.replace("+asyncpg", "")
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
        context.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA_NAME}"')
        context.execute(f'SET search_path TO "{SCHEMA_NAME}"')
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
        # Les migrations existantes ecrivent des noms non qualifies (`op.create_table("user")`,
        # `ALTER TYPE ...`) : le search_path les range dans le schema.
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA_NAME}"'))
        connection.execute(text(f'SET search_path TO "{SCHEMA_NAME}"'))
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(
        _settings.async_database_url,
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
