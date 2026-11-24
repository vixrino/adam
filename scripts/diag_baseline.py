"""
scripts/diag_baseline.py
------------------------
Lecture seule. Pour une base creee avant la baseline release_1 : dit ou est
rangee la version Alembic, et ce qui separe la base des modeles actuels.

Le launcher echoue alors avec « relation "file" already exists » : il ne
trouve aucune version dans <schema>.alembic_version et rejoue release_1 sur
des tables qui existent deja.

Usage :
    uv run --all-extras python scripts/diag_baseline.py
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def _module(nom: str) -> Any:
    cores = sorted(p.name for p in SRC.glob("*_core") if (p / "models").is_dir())
    if len(cores) != 1:
        raise SystemExit(f"attendu un *_core sous src/, trouve {cores}")
    return importlib.import_module(f"{cores[0].removesuffix('_core')}_{nom}")


def main() -> None:
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine, text

    os.environ.pop("POSTGRES_DB", None)
    _module("core.models")  # enregistre toutes les tables dans Base.metadata
    base = _module("core.db.base").Base
    schema = base.metadata.schema
    core = _module("core.core.config").get_core_settings()
    url = core.migration_database_url.replace("+asyncpg", "+psycopg2")
    print(f"Base : {core.postgres_db}   schema : {schema}\n")

    with create_engine(url).connect() as conn:
        print("== tables alembic_version")
        lieux = (
            conn.execute(
                text(
                    "SELECT table_schema FROM information_schema.tables "
                    "WHERE table_name = 'alembic_version' ORDER BY 1"
                )
            )
            .scalars()
            .all()
        )
        if not lieux:
            print("  aucune")
        for lieu in lieux:
            versions = (
                conn.execute(text(f'SELECT version_num FROM "{lieu}".alembic_version'))
                .scalars()
                .all()
            )
            print(f"  {lieu}.alembic_version : {versions or 'vide'}")

        print(f"\n== tables du schema {schema}")
        tables = (
            conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :s ORDER BY 1"
                ),
                {"s": schema},
            )
            .scalars()
            .all()
        )
        print("  " + ", ".join(tables))

        print("\n== lignes par table metier")
        for nom in ("document", "document_field", "field_proposal", "test_execution"):
            if nom in tables:
                n = conn.execute(text(f'SELECT count(*) FROM "{schema}"."{nom}"')).scalar_one()
                print(f"  {nom:<16} {n}")

        print("\n== ecarts entre la base et les modeles (ce qu'Alembic voudrait changer)")
        contexte = MigrationContext.configure(
            conn,
            opts={
                "include_schemas": True,
                "include_name": lambda n, t, _p: n == schema if t == "schema" else True,
                "version_table_schema": schema,
                "compare_type": True,
            },
        )
        ecarts = compare_metadata(contexte, base.metadata)
        if not ecarts:
            print("  aucun")
        for ecart in ecarts:
            print(f"  {_decrire(ecart[0] if isinstance(ecart, list) else ecart)}")


def _decrire(ecart: tuple[Any, ...]) -> str:
    op = ecart[0]
    if op in ("add_table", "remove_table"):
        cible = ecart[1].name
    elif op in ("add_column", "remove_column"):
        cible = f"{ecart[2]}.{ecart[3].name}"
    elif op.startswith("modify_"):
        cible = f"{ecart[2]}.{ecart[3]}"
    else:
        objet = ecart[1]
        table = getattr(getattr(objet, "table", None), "name", "?")
        cible = f"{table}.{getattr(objet, 'name', objet)}"
    return f"{op:<22} {cible}"


if __name__ == "__main__":
    main()
