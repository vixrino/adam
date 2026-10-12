"""
scripts/migrer_expected_page_count.py
-------------------------------------
Met une base au niveau de Dataset.expected_page_count, en une commande :

  1. cree la migration alembic qui ajoute la colonne dataset.expected_page_count,
     branchee sur la tete actuelle des migrations (rien n'est cree si une
     migration l'ajoute deja) ;
  2. applique les migrations (alembic upgrade head) ;
  3. fixe le nombre de pages exige sur le ou les datasets CERFA.

Le paquet *_core (nota_core ou adam_core) et son alembic.ini sont trouves sous
src/ : le script tourne tel quel dans les deux depots. Il se lance depuis la
racine du depot, la ou se trouve le .env.

Usage :
    python scripts/migrer_expected_page_count.py --dry-run
    python scripts/migrer_expected_page_count.py
    python scripts/migrer_expected_page_count.py --dataset-id 3 --dataset-id 7
    python scripts/migrer_expected_page_count.py --fichier-seul

Par defaut, les datasets vises sont ceux nommes cerfa_13594-02_v2 (le nom que
leur donne le seed) dont expected_page_count est encore vide : relancer le
script ne change rien a un dataset deja regle a la main.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402

COLONNE = "expected_page_count"
CERFA_DATASET_NAME = "cerfa_13594-02_v2"
CERFA_PAGE_COUNT = 12

MIGRATION = '''"""add dataset.expected_page_count

Le nombre de pages exige des PDF ingeres etait un reglage global
(INGESTION_PAGE_COUNT). Un dataset porte un type de document, et tous n'ont
pas le meme nombre de pages : le controle est donc porte par le dataset.
NULL = aucun controle, comportement inchange pour les datasets existants.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "{revision}"
down_revision: Union[str, None] = "{down_revision}"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset",
        sa.Column(
            "expected_page_count",
            sa.Integer(),
            nullable=True,
            comment=(
                "Nombre de pages exige des PDF ingeres (12 pour le CERFA) ; NULL = "
                "aucun controle. Un PDF hors taille est cree en ERROR."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("dataset", "expected_page_count")
'''


def _paquet_core() -> Tuple[str, Path]:
    """Nom du paquet *_core et chemin de son alembic.ini."""
    trouves = sorted(p.parent for p in SRC.glob("*_core/alembic.ini"))
    if len(trouves) != 1:
        raise SystemExit(
            f"attendu un seul src/*_core/alembic.ini, trouve {len(trouves)} : "
            f"{[str(p) for p in trouves]}"
        )
    return trouves[0].name, trouves[0] / "alembic.ini"


def _migration_existante(versions: Path) -> Optional[Path]:
    """Migration qui ajoute deja la colonne, s'il y en a une."""
    for fichier in sorted(versions.glob("*.py")):
        texte = fichier.read_text(encoding="utf-8")
        if "add_column" in texte and f'"{COLONNE}"' in texte and '"dataset"' in texte:
            return fichier
    return None


def creer_migration(alembic_ini: Path, dry_run: bool) -> None:
    cfg = Config(str(alembic_ini))
    script = ScriptDirectory.from_config(cfg)
    versions = Path(script.versions)

    existante = _migration_existante(versions)
    if existante is not None:
        print(f" [1/3] migration deja presente, rien a creer : {existante.name}")
        return

    tetes = script.get_heads()
    if len(tetes) != 1:
        raise SystemExit(
            f" [1/3] {len(tetes)} tetes de migration ({', '.join(tetes)}) : impossible de "
            "savoir ou brancher la nouvelle. Fusionner d'abord les tetes "
            "(alembic merge heads), puis relancer."
        )
    tete = tetes[0]
    revision = uuid.uuid4().hex[:12]
    horodatage = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    fichier = versions / f"{horodatage}_{revision}_add_dataset_expected_page_count.py"

    if dry_run:
        print(f" [1/3] (dry-run) creerait {fichier.name}, branchee sur {tete}")
        return
    fichier.write_text(MIGRATION.format(revision=revision, down_revision=tete), encoding="utf-8")
    print(f" [1/3] migration creee : {fichier.name} (apres {tete})")


def appliquer_migrations(alembic_ini: Path, dry_run: bool) -> None:
    if dry_run:
        print(" [2/3] (dry-run) lancerait alembic upgrade head")
        return
    print(" [2/3] alembic upgrade head...")
    command.upgrade(Config(str(alembic_ini)), "head")
    print("        base a jour")


async def regler_datasets(core: str, dataset_ids: List[int], pages: int, dry_run: bool) -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    settings = importlib.import_module(f"{core}.core.config").get_core_settings()
    engine = create_async_engine(settings.async_database_url)
    try:
        async with engine.begin() as conn:
            if dataset_ids:
                cibles = (
                    await conn.execute(
                        text(
                            f"SELECT id, name, {COLONNE} FROM dataset "
                            "WHERE id = ANY(:ids) ORDER BY id"
                        ),
                        {"ids": dataset_ids},
                    )
                ).all()
            else:
                cibles = (
                    await conn.execute(
                        text(
                            f"SELECT id, name, {COLONNE} FROM dataset "
                            f"WHERE name = :name AND {COLONNE} IS NULL ORDER BY id"
                        ),
                        {"name": CERFA_DATASET_NAME},
                    )
                ).all()

            if not cibles:
                tous = (await conn.execute(text("SELECT id, name FROM dataset ORDER BY id"))).all()
                print(" [3/3] aucun dataset a regler. Datasets presents :")
                for ligne in tous:
                    print(f"        id={ligne.id}  {ligne.name}")
                print("        relancer avec --dataset-id <id> pour en viser un.")
                return

            for ligne in cibles:
                action = "(dry-run) reglerait" if dry_run else "regle"
                print(
                    f" [3/3] {action} dataset id={ligne.id} {ligne.name} : "
                    f"{ligne.expected_page_count} -> {pages} pages"
                )
            if not dry_run:
                await conn.execute(
                    text(f"UPDATE dataset SET {COLONNE} = :pages WHERE id = ANY(:ids)"),
                    {"pages": pages, "ids": [ligne.id for ligne in cibles]},
                )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("Usage")[0])
    parser.add_argument("--dry-run", action="store_true", help="Montre sans rien ecrire")
    parser.add_argument(
        "--fichier-seul",
        action="store_true",
        help="Cree seulement le fichier de migration, sans toucher a la base",
    )
    parser.add_argument(
        "--dataset-id",
        type=int,
        action="append",
        default=[],
        help=f"Dataset a regler (repetable). Defaut : ceux nommes {CERFA_DATASET_NAME}",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=CERFA_PAGE_COUNT,
        help=f"Nombre de pages exige (defaut {CERFA_PAGE_COUNT})",
    )
    args = parser.parse_args()

    core, alembic_ini = _paquet_core()
    print(f" Paquet : {core}  ({alembic_ini.relative_to(ROOT)})")
    creer_migration(alembic_ini, args.dry_run)
    if args.fichier_seul:
        return
    appliquer_migrations(alembic_ini, args.dry_run)
    asyncio.run(regler_datasets(core, args.dataset_id, args.pages, args.dry_run))


if __name__ == "__main__":
    main()
