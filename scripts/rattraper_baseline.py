"""
scripts/rattraper_baseline.py
-----------------------------
Rattache a la baseline release_1 une base creee avec l'ancienne chaine de
migrations, sans perdre l'annotation.

Symptome : le launcher echoue sur « relation "file" already exists ».
L'ancienne chaine rangeait la version dans public.alembic_version ; le code
actuel la cherche dans <schema>.alembic_version, la trouve vide et rejoue
release_1 sur des tables existantes.

Ce que fait le script, dans une seule transaction :
1. ajoute ce que les modeles ont et que la base n'a pas (tables, colonnes,
   index, contraintes) et elargit les types (Integer -> BigInteger). Rien
   n'est supprime : une table ou colonne en trop dans la base reste la ;
2. ocr_result.provider (NOT NULL, sans defaut) est rempli depuis
   dataset.ocr_provider avant de passer NOT NULL ;
3. ecrit dans <schema>.alembic_version la revision de public.alembic_version
   si le code la connait (le launcher applique alors la suite), sinon la
   derniere revision du code (head) : apres l'etape 1, la base a tout ce que
   les modeles demandent.

Une modification refusee par la base (ex. contrainte d'unicite violee par
des doublons) est annulee seule et listee a la fin ; le reste passe.

Sans --appliquer, tout est joue puis annule (apercu). Lancer d'abord
diag_baseline.py, avec le code a jour.

Usage :
    uv run --all-extras python scripts/rattraper_baseline.py              # apercu
    uv run --all-extras python scripts/rattraper_baseline.py --appliquer
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path
from typing import Any, Iterator, List

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def _module(nom: str) -> Any:
    cores = sorted(p.name for p in SRC.glob("*_core") if (p / "models").is_dir())
    if len(cores) != 1:
        raise SystemExit(f"attendu un *_core sous src/, trouve {cores}")
    return importlib.import_module(f"{cores[0].removesuffix('_core')}_{nom}")


def _a_plat(operations: Any) -> Iterator[Any]:
    for op in operations.ops:
        if hasattr(op, "ops"):  # ModifyTableOps : les operations d'une table
            yield from _a_plat(op)
        else:
            yield op


def _decrire(op: Any) -> str:
    nom = type(op).__name__.removesuffix("Op")
    table = getattr(op, "table_name", None)
    objet = (
        getattr(op, "column_name", None)
        or getattr(getattr(op, "column", None), "name", None)
        or getattr(op, "index_name", None)
        or getattr(op, "constraint_name", None)
        or ""
    )
    return f"{nom:<24} {table}{'.' + objet if objet else ''}"


def rattraper(appliquer: bool) -> None:
    from alembic.autogenerate import produce_migrations
    from alembic.operations import Operations
    from alembic.operations import ops as alembic_ops
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine, text

    _module("core.models")
    base = _module("core.db.base").Base
    schema = base.metadata.schema
    core = _module("core.core.config").get_core_settings()
    scripts = ScriptDirectory.from_config(_module("core.db.migrate").alembic_config())
    revisions = {r.revision for r in scripts.walk_revisions()}
    heads = scripts.get_heads()
    if len(heads) != 1:
        raise SystemExit(f"le code a {len(heads)} heads Alembic ({heads}) : a corriger d'abord")
    head = heads[0]
    print(f"Base : {core.postgres_db}   schema : {schema}\n")

    ajouts = (
        alembic_ops.CreateTableOp,
        alembic_ops.AddColumnOp,
        alembic_ops.CreateIndexOp,
        alembic_ops.CreateUniqueConstraintOp,
        alembic_ops.CreateForeignKeyOp,
        alembic_ops.AlterColumnOp,
    )
    url = core.migration_database_url.replace("+asyncpg", "+psycopg2")
    # Cf. diag_baseline.py : le schema ne doit pas etre le schema par defaut.
    engine = create_engine(url, connect_args={"options": "-c search_path=public"})
    with engine.connect() as conn:
        transaction = conn.begin()
        deja = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :s AND table_name = 'alembic_version'"
            ),
            {"s": schema},
        ).first()
        if deja and conn.execute(text(f'SELECT 1 FROM "{schema}".alembic_version')).first():
            print(f"{schema}.alembic_version est deja rempli : rien a faire, lancez le launcher.")
            return
        ancienne = None
        if conn.execute(text("SELECT to_regclass('public.alembic_version')")).scalar():
            ancienne = conn.execute(text("SELECT version_num FROM public.alembic_version")).scalar()
        version = ancienne if ancienne in revisions else head
        print(f"public.alembic_version : {ancienne!r}  ->  version retenue : {version}\n")

        contexte = MigrationContext.configure(
            conn,
            opts={
                "include_schemas": True,
                "include_name": lambda n, t, _p: n == schema if t == "schema" else True,
                "version_table_schema": schema,
                "compare_type": True,
            },
        )
        operations = Operations(contexte)
        a_faire: List[Any] = []
        ignores: List[Any] = []
        toutes = list(_a_plat(produce_migrations(contexte, base.metadata).upgrade_ops))
        # Un index que les modeles nomment autrement existe deja : ne pas le doubler.
        renommes = {
            (op.table_name, tuple(str(c) for c in op.to_index().expressions))
            for op in toutes
            if isinstance(op, alembic_ops.DropIndexOp)
        }
        for op in toutes:
            if (
                isinstance(op, alembic_ops.CreateIndexOp)
                and (
                    op.table_name,
                    tuple(str(c) for c in op.to_index().expressions),
                )
                in renommes
            ):
                ignores.append(op)
            elif isinstance(op, ajouts):
                a_faire.append(op)
            else:
                ignores.append(op)

        print("== ajouts et elargissements")
        creees = set()
        refuses: List[str] = []
        for op in a_faire:
            print(f"  {_decrire(op)}")
            point = conn.begin_nested()
            try:
                _appliquer(op, conn, operations, base, schema, creees)
                point.commit()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                point.rollback()
                refuses.append(f"  {_decrire(op)}\n      {str(exc).splitlines()[0]}")
        if not a_faire:
            print("  aucun")

        print("\n== laisses tels quels (suppressions, index deja presents sous un autre nom)")
        for op in ignores:
            print(f"  {_decrire(op)}")
        if not ignores:
            print("  aucun")
        if refuses:
            print(f"\n== REFUSES par la base ({len(refuses)}), a traiter a la main")
            print("\n".join(refuses))

        conn.execute(
            text(
                f'CREATE TABLE IF NOT EXISTS "{schema}".alembic_version ('
                "version_num VARCHAR(32) NOT NULL, "
                "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
            )
        )
        conn.execute(
            text(f'INSERT INTO "{schema}".alembic_version (version_num) VALUES (:v)'),
            {"v": version},
        )
        print(f"\n== version : {schema}.alembic_version = {version}")

        if not appliquer:
            transaction.rollback()
            print("\n(sans --appliquer) tout a ete annule.")
            return
        transaction.commit()
    print("\nBase rattachee. Lancez : uv run python launcher.py")


def _appliquer(op: Any, conn: Any, operations: Any, base: Any, schema: str, creees: set) -> None:
    from alembic.operations import ops as alembic_ops
    from sqlalchemy import Column, String, text

    if isinstance(op, alembic_ops.CreateTableOp):
        # La table des modeles, et non l'op : celle-ci perd le schema des cles
        # etrangeres (REFERENCES "user" au lieu de nota."user"). Ses index suivent.
        base.metadata.tables[f"{schema}.{op.table_name}"].create(conn)
        creees.add(op.table_name)
        return
    if isinstance(op, alembic_ops.CreateIndexOp) and op.table_name in creees:
        return
    if (
        isinstance(op, alembic_ops.AddColumnOp)
        and op.table_name == "ocr_result"
        and op.column.name == "provider"
    ):
        operations.add_column(
            "ocr_result",
            Column("provider", String, nullable=True, comment=op.column.comment),
            schema=schema,
        )
        conn.execute(
            text(
                f'UPDATE "{schema}".ocr_result o SET provider = COALESCE('
                f'(SELECT d.ocr_provider FROM "{schema}".dataset d '
                "WHERE d.id = o.dataset_id), 'MISTRAL')"
            )
        )
        operations.alter_column("ocr_result", "provider", nullable=False, schema=schema)
        return
    operations.invoke(op)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--appliquer", action="store_true", help="Ecrire (sinon : apercu)")
    args = parser.parse_args()
    os.environ.pop("POSTGRES_DB", None)
    rattraper(args.appliquer)


if __name__ == "__main__":
    main()
