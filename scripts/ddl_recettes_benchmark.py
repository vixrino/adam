"""
scripts/ddl_recettes_benchmark.py
---------------------------------
Met une base au niveau des recettes de benchmark depuis un export : table
dataset_export, colonnes dataset_export_id, tout_l_export, version et
recette_racine_id sur test_recipe, unicite (dataset_id, name, version).

Pour une base qui n'est pas suivie par Alembic (nota : creee par create_all) ;
dans adam, c'est la migration d0e1f2a3b4c5. Rejouable : chaque etape verifie
d'abord ce qui existe. Le schema Postgres est celui des modeles (« nota » dans
nota, public dans adam).

Le paquet *_core est trouve sous src/ : le script tourne tel quel dans adam et
dans nota, depuis la racine du depot (.env).

Usage :
    python scripts/ddl_recettes_benchmark.py --dry-run   # affiche le SQL
    python scripts/ddl_recettes_benchmark.py
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import sys
from pathlib import Path
from typing import Any, List

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def _prefixe() -> str:
    """'adam' ou 'nota', d'apres le paquet *_core present sous src/."""
    cores = sorted(p.name for p in SRC.glob("*_core") if (p / "models").is_dir())
    if len(cores) != 1:
        raise SystemExit(f"attendu un *_core sous src/, trouve {cores}")
    return cores[0].removesuffix("_core")


def _q(schema: Any, table: str) -> str:
    return f'"{schema}"."{table}"' if schema else f'"{table}"'


def instructions(schema: Any) -> List[str]:
    """Le DDL, rejouable, de test_recipe (dataset_export est cree a part)."""
    recette, export = _q(schema, "test_recipe"), _q(schema, "dataset_export")
    nom_schema = schema or "public"
    contrainte = (
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint c "
        "JOIN pg_namespace n ON n.oid = c.connamespace "
        f"WHERE c.conname = '{{nom}}' AND n.nspname = '{nom_schema}') THEN "
        f"ALTER TABLE {recette} ADD CONSTRAINT {{nom}} {{definition}}; END IF; END $$"
    )
    return [
        f"ALTER TABLE {recette} ADD COLUMN IF NOT EXISTS dataset_export_id INTEGER",
        f"ALTER TABLE {recette} ADD COLUMN IF NOT EXISTS tout_l_export BOOLEAN "
        "NOT NULL DEFAULT false",
        f"ALTER TABLE {recette} ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
        f"ALTER TABLE {recette} ADD COLUMN IF NOT EXISTS recette_racine_id INTEGER",
        contrainte.format(
            nom="fk_test_recipe_dataset_export_id_dataset_export",
            definition=f"FOREIGN KEY (dataset_export_id) REFERENCES {export} (id) "
            "ON DELETE RESTRICT",
        ),
        contrainte.format(
            nom="fk_test_recipe_recette_racine_id_test_recipe",
            definition=f"FOREIGN KEY (recette_racine_id) REFERENCES {recette} (id) "
            "ON DELETE RESTRICT",
        ),
        "CREATE INDEX IF NOT EXISTS ix_test_recipe_dataset_export_id "
        f"ON {recette} (dataset_export_id)",
        "CREATE INDEX IF NOT EXISTS ix_test_recipe_recette_racine_id "
        f"ON {recette} (recette_racine_id)",
        f"ALTER TABLE {recette} DROP CONSTRAINT IF EXISTS uq_test_recipe_dataset_name",
        contrainte.format(
            nom="uq_test_recipe_dataset_name_version",
            definition="UNIQUE (dataset_id, name, version)",
        ),
    ]


async def appliquer(dry_run: bool) -> None:
    from sqlalchemy import text

    p = _prefixe()
    modeles = importlib.import_module(f"{p}_core.models")
    session_mod = importlib.import_module(f"{p}_core.db.session")
    core = importlib.import_module(f"{p}_core.core.config").get_core_settings()
    schema = modeles.TestRecipe.__table__.schema
    ddl = instructions(schema)
    if dry_run:
        print(f"-- dataset_export : CREATE TABLE IF NOT EXISTS {_q(schema, 'dataset_export')}")
        print(";\n".join(ddl) + ";")
        return
    session_mod.init_engine(core.async_database_url)
    moteur = session_mod.get_engine()
    async with moteur.begin() as connexion:
        await connexion.run_sync(
            lambda sync: modeles.DatasetExport.__table__.create(sync, checkfirst=True)
        )
        for instruction in ddl:
            await connexion.execute(text(instruction))
    await moteur.dispose()
    print(f" base a jour : dataset_export et test_recipe ({schema or 'public'})")


def main() -> None:
    """Point d'entree en ligne de commande."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="Affiche le SQL sans l'executer")
    asyncio.run(appliquer(parser.parse_args().dry_run))


if __name__ == "__main__":
    main()
