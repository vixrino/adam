"""
scripts/migrer_expected_page_count.py
-------------------------------------
Met une base au niveau de Dataset.expected_page_count, en une commande :

  1. cree la migration alembic qui ajoute la colonne dataset.expected_page_count,
     branchee sur la tete actuelle des migrations (rien n'est cree si une
     migration l'ajoute deja). S'il y a plusieurs tetes, une migration de
     fusion les reunit d'abord ;
  2. met la base au niveau : alembic upgrade head si la base est suivie par
     alembic ; sinon (tables creees par le seed), ajout direct de la colonne,
     un upgrade y rejouant toutes les migrations sur des tables existantes ;
  3. fixe le nombre de pages exige sur le ou les datasets CERFA.

Le paquet *_core (adam_core) et son alembic.ini sont trouves sous
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
from typing import Any, List, Optional, Tuple

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
    """Cree la migration, apres avoir fusionne les tetes s'il y en a plusieurs.

    Plusieurs tetes : deux branches de migrations developpees en parallele. La
    nouvelle ne peut se brancher que sur une tete unique ; une migration de
    fusion vide (alembic merge heads) les reunit d'abord. Elle ne touche pas
    a la base, seulement a l'historique.
    """
    cfg = Config(str(alembic_ini))
    script = ScriptDirectory.from_config(cfg)
    versions = Path(script.versions)

    existante = _migration_existante(versions)
    if existante is not None:
        print(f" [1/3] migration deja presente, rien a creer : {existante.name}")
        return

    tetes = list(script.get_heads())
    if len(tetes) > 1:
        if dry_run:
            print(f" [1/3] (dry-run) fusionnerait les tetes {', '.join(tetes)}")
            tete = "<fusion>"
        else:
            fusion = command.merge(cfg, revisions=tetes, message="merge heads")
            tete = fusion.revision if fusion is not None else ""
            print(f" [1/3] tetes {', '.join(tetes)} fusionnees : {tete}")
            script = ScriptDirectory.from_config(cfg)
            if list(script.get_heads()) != [tete]:
                raise SystemExit("        la fusion n'a pas laisse une tete unique, arret")
    else:
        tete = tetes[0]

    revision = uuid.uuid4().hex[:12]
    horodatage = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    fichier = versions / f"{horodatage}_{revision}_add_dataset_expected_page_count.py"

    if dry_run:
        print(f" [1/3] (dry-run) creerait {fichier.name}, branchee sur {tete}")
        return
    fichier.write_text(MIGRATION.format(revision=revision, down_revision=tete), encoding="utf-8")
    print(f" [1/3] migration creee : {fichier.name} (apres {tete})")


def _engine(core: str) -> Any:
    from sqlalchemy.ext.asyncio import create_async_engine

    settings = importlib.import_module(f"{core}.core.config").get_core_settings()
    # Les tables vivent dans le schema nota : le search_path lui laisse ecrire `dataset` tout court.
    return create_async_engine(
        settings.async_database_url,
        connect_args={"server_settings": {"search_path": "nota"}},
    )


async def _etat_base(core: str) -> Tuple[List[str], bool]:
    """(versions alembic enregistrees en base, colonne deja presente)."""
    from sqlalchemy import text

    engine = _engine(core)
    try:
        async with engine.connect() as conn:
            suivie = (
                await conn.execute(text("SELECT to_regclass('alembic_version') IS NOT NULL"))
            ).scalar_one()
            versions = (
                [r[0] for r in await conn.execute(text("SELECT version_num FROM alembic_version"))]
                if suivie
                else []
            )
            colonne = (
                await conn.execute(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = 'dataset' AND column_name = :c)"
                    ),
                    {"c": COLONNE},
                )
            ).scalar_one()
        return versions, bool(colonne)
    finally:
        await engine.dispose()


async def _ajouter_colonne(core: str) -> None:
    from sqlalchemy import text

    engine = _engine(core)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(f"ALTER TABLE dataset ADD COLUMN IF NOT EXISTS {COLONNE} INTEGER")
            )
    finally:
        await engine.dispose()


def appliquer(core: str, alembic_ini: Path, dry_run: bool) -> bool:
    """Met la base au niveau ; rend True si la colonne existe a la fin.

    Une base suivie par alembic (table alembic_version renseignee) recoit un
    upgrade head. Une base creee par le seed, via create_all, ne l'est pas :
    upgrade y rejouerait toutes les migrations depuis le debut, sur des tables
    qui existent deja. La colonne y est alors ajoutee directement.
    """
    versions, colonne = asyncio.run(_etat_base(core))
    if versions:
        if dry_run:
            print(f" [2/3] (dry-run) base suivie ({', '.join(versions)}) : alembic upgrade head")
            return colonne
        print(f" [2/3] base suivie ({', '.join(versions)}) : alembic upgrade head...")
        command.upgrade(Config(str(alembic_ini)), "head")
        return True

    print(
        " [2/3] base non suivie par alembic (aucune version enregistree : tables "
        "creees par le seed). Pas d'upgrade, qui rejouerait toutes les migrations."
    )
    if colonne:
        print(f"        colonne dataset.{COLONNE} deja presente")
        return True
    if dry_run:
        print(f"        (dry-run) ajouterait la colonne dataset.{COLONNE}")
        return False
    asyncio.run(_ajouter_colonne(core))
    print(f"        colonne dataset.{COLONNE} ajoutee")
    return True


async def regler_datasets(
    core: str, dataset_ids: List[int], pages: int, dry_run: bool, colonne: bool
) -> None:
    from sqlalchemy import text

    # En dry-run sur une base qui n'a pas encore la colonne, on ne peut pas la
    # lire : on montre les datasets vises, valeur actuelle inconnue (NULL).
    valeur = COLONNE if colonne else "NULL"
    filtre_vide = f"AND {COLONNE} IS NULL" if colonne else ""
    engine = _engine(core)
    try:
        async with engine.begin() as conn:
            if dataset_ids:
                cibles = (
                    await conn.execute(
                        text(
                            f"SELECT id, name, {valeur} AS actuel FROM dataset "
                            "WHERE id = ANY(:ids) ORDER BY id"
                        ),
                        {"ids": dataset_ids},
                    )
                ).all()
            else:
                cibles = (
                    await conn.execute(
                        text(
                            f"SELECT id, name, {valeur} AS actuel FROM dataset "
                            f"WHERE name = :name {filtre_vide} ORDER BY id"
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
                    f"{ligne.actuel} -> {pages} pages"
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
    colonne = appliquer(core, alembic_ini, args.dry_run)
    asyncio.run(regler_datasets(core, args.dataset_id, args.pages, args.dry_run, colonne))


if __name__ == "__main__":
    main()