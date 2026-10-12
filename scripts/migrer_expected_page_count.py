"""
scripts/migrer_expected_page_count.py
-------------------------------------
Met une base au niveau des derniers changements de modele, en une commande :

  - dataset.expected_page_count : nombre de pages exige des PDF ingeres ;
  - schema_page : description de chaque page d'un schema, qui sert a
    reconnaitre les pages et a les remettre en ordre (extraction generique) ;
  - field_spec.description : ce que le champ contient, dit au moteur OCR.

Etapes :
  1. cree les migrations alembic manquantes, branchees sur la tete actuelle
     (une migration de fusion reunit d'abord les tetes s'il y en a plusieurs ;
     rien n'est cree pour un changement qu'une migration couvre deja) ;
  2. met la base au niveau : alembic upgrade head si la base est suivie par
     alembic ; sinon (tables creees par le seed), DDL direct, un upgrade y
     rejouant toutes les migrations sur des tables existantes ;
  3. fixe le nombre de pages exige sur le ou les datasets CERFA ;
  4. decrit les 12 pages des schemas CERFA deja en base et complete la
     description de leurs champs, d'apres cerfa_v2 : sans re-seeder, donc
     sans toucher aux documents.

Le paquet *_core (nota_core ou adam_core) et son alembic.ini sont trouves sous
src/ : le script tourne tel quel dans les deux depots. Il se lance depuis la
racine du depot, la ou se trouve le .env. Le relancer ne refait rien de ce qui
est deja fait.

Usage :
    python scripts/migrer_expected_page_count.py --dry-run
    python scripts/migrer_expected_page_count.py
    python scripts/migrer_expected_page_count.py --dataset-id 3 --dataset-id 7
    python scripts/migrer_expected_page_count.py --fichier-seul
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402

CERFA_DATASET_NAME = "cerfa_13594-02_v2"
CERFA_DOCUMENT_TYPE = "CERFA_SURENDETTEMENT_V2"
CERFA_PAGE_COUNT = 12

_ENTETE = '''"""{titre}

{explication}
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "{{revision}}"
down_revision: Union[str, None] = "{{down_revision}}"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

'''

MIGRATION_PAGE_COUNT = (
    _ENTETE.format(
        titre="add dataset.expected_page_count",
        explication=(
            "Le nombre de pages exige des PDF ingeres est porte par le dataset :\n"
            "tous les types de document n'ont pas le meme. NULL = aucun controle."
        ),
    )
    + """
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
"""
)

MIGRATION_SCHEMA_PAGE = (
    _ENTETE.format(
        titre="add schema_page",
        explication=(
            "Extraction OCR generique : chaque page d'un schema est decrite par ses\n"
            "titres de rubrique imprimes, pour reconnaitre une page a son contenu et\n"
            "remettre en ordre un document scanne dans le desordre.\n"
            "field_spec.description est ajoutee si elle manque : elle existe deja la\n"
            "ou la migration 289059f04c71 est passee."
        ),
    )
    + """
def upgrade() -> None:
    op.execute("ALTER TABLE field_spec ADD COLUMN IF NOT EXISTS description TEXT")
    op.create_table(
        "schema_page",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "schema_id",
            sa.Integer(),
            sa.ForeignKey("doc_schema.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False, comment="1-indexe"),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            comment="Titres de rubrique imprimes, qui servent a reconnaitre la page",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("schema_id", "page_number", name="uq_schema_page_schema_number"),
    )
    op.create_index("ix_schema_page_schema_id", "schema_page", ["schema_id"])


def downgrade() -> None:
    op.drop_index("ix_schema_page_schema_id", table_name="schema_page")
    op.drop_table("schema_page")
"""
)

#: DDL direct pour une base non suivie par alembic, rejouable sans effet.
DDL_DIRECT = [
    "ALTER TABLE dataset ADD COLUMN IF NOT EXISTS expected_page_count INTEGER",
    "ALTER TABLE field_spec ADD COLUMN IF NOT EXISTS description TEXT",
    """
    CREATE TABLE IF NOT EXISTS schema_page (
        id SERIAL PRIMARY KEY,
        schema_id INTEGER NOT NULL REFERENCES doc_schema (id) ON DELETE CASCADE,
        page_number INTEGER NOT NULL,
        description TEXT NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
        CONSTRAINT uq_schema_page_schema_number UNIQUE (schema_id, page_number)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_schema_page_schema_id ON schema_page (schema_id)",
]


@dataclass(frozen=True)
class Changement:
    """Un changement de modele et la migration qui le porte."""

    slug: str
    contenu: str
    #: Reconnait, dans le texte d'une migration existante, qu'elle le couvre deja.
    deja_couvert: Callable[[str], bool]


CHANGEMENTS = [
    Changement(
        slug="add_dataset_expected_page_count",
        contenu=MIGRATION_PAGE_COUNT,
        deja_couvert=lambda t: (
            "add_column" in t and '"expected_page_count"' in t and '"dataset"' in t
        ),
    ),
    Changement(
        slug="add_schema_page",
        contenu=MIGRATION_SCHEMA_PAGE,
        deja_couvert=lambda t: "create_table" in t and '"schema_page"' in t,
    ),
]


def _paquet_core() -> Tuple[str, Path]:
    """Nom du paquet *_core et chemin de son alembic.ini."""
    trouves = sorted(p.parent for p in SRC.glob("*_core/alembic.ini"))
    if len(trouves) != 1:
        raise SystemExit(
            f"attendu un seul src/*_core/alembic.ini, trouve {len(trouves)} : "
            f"{[str(p) for p in trouves]}"
        )
    return trouves[0].name, trouves[0] / "alembic.ini"


def _deja_couvert(versions: Path, changement: Changement) -> Optional[Path]:
    for fichier in sorted(versions.glob("*.py")):
        if changement.deja_couvert(fichier.read_text(encoding="utf-8")):
            return fichier
    return None


# -- 1. Migrations ---------------------------------------------------------------


def creer_migrations(alembic_ini: Path, dry_run: bool) -> None:
    """Cree les migrations manquantes, chainees les unes aux autres."""
    cfg = Config(str(alembic_ini))
    script = ScriptDirectory.from_config(cfg)
    versions = Path(script.versions)

    a_creer = []
    for changement in CHANGEMENTS:
        existante = _deja_couvert(versions, changement)
        if existante is not None:
            print(f" [1/4] {changement.slug} : deja couvert par {existante.name}")
        else:
            a_creer.append(changement)
    if not a_creer:
        return

    tetes = list(script.get_heads())
    if len(tetes) > 1:
        # Deux branches developpees en parallele : la fusion les reunit, sans
        # toucher a la base, pour que la suite se branche sur une tete unique.
        if dry_run:
            print(f" [1/4] (dry-run) fusionnerait les tetes {', '.join(tetes)}")
            tete = "<fusion>"
        else:
            fusion = command.merge(cfg, revisions=tetes, message="merge heads")
            tete = fusion.revision if fusion is not None else ""
            print(f" [1/4] tetes {', '.join(tetes)} fusionnees : {tete}")
            if list(ScriptDirectory.from_config(cfg).get_heads()) != [tete]:
                raise SystemExit("        la fusion n'a pas laisse une tete unique, arret")
    else:
        tete = tetes[0]

    horodatage = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    for rang, changement in enumerate(a_creer):
        revision = uuid.uuid4().hex[:12]
        # Le rang dans le nom garde l'ordre de lecture quand l'horodatage est le meme.
        fichier = versions / f"{horodatage}{rang}_{revision}_{changement.slug}.py"
        if dry_run:
            print(f" [1/4] (dry-run) creerait {fichier.name}, apres {tete}")
        else:
            fichier.write_text(
                changement.contenu.format(revision=revision, down_revision=tete),
                encoding="utf-8",
            )
            print(f" [1/4] migration creee : {fichier.name} (apres {tete})")
        tete = revision


# -- 2. Base -----------------------------------------------------------------------


def _engine(core: str) -> Any:
    from sqlalchemy.ext.asyncio import create_async_engine

    settings = importlib.import_module(f"{core}.core.config").get_core_settings()
    return create_async_engine(settings.async_database_url)


async def _versions_alembic(core: str) -> List[str]:
    from sqlalchemy import text

    engine = _engine(core)
    try:
        async with engine.connect() as conn:
            suivie = (
                await conn.execute(text("SELECT to_regclass('alembic_version') IS NOT NULL"))
            ).scalar_one()
            if not suivie:
                return []
            lignes = await conn.execute(text("SELECT version_num FROM alembic_version"))
            return [r[0] for r in lignes]
    finally:
        await engine.dispose()


async def _etat(core: str) -> Dict[str, bool]:
    """Quelles colonnes et tables du changement existent deja en base."""
    from sqlalchemy import text

    requete_colonne = text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c)"
    )
    engine = _engine(core)
    try:
        async with engine.connect() as conn:
            page_count = await conn.execute(
                requete_colonne, {"t": "dataset", "c": "expected_page_count"}
            )
            description = await conn.execute(
                requete_colonne, {"t": "field_spec", "c": "description"}
            )
            schema_page = await conn.execute(text("SELECT to_regclass('schema_page') IS NOT NULL"))
            return {
                "expected_page_count": bool(page_count.scalar_one()),
                "description": bool(description.scalar_one()),
                "schema_page": bool(schema_page.scalar_one()),
            }
    finally:
        await engine.dispose()


async def _ddl_direct(core: str) -> None:
    from sqlalchemy import text

    engine = _engine(core)
    try:
        async with engine.begin() as conn:
            for instruction in DDL_DIRECT:
                await conn.execute(text(instruction))
    finally:
        await engine.dispose()


def mettre_au_niveau(core: str, alembic_ini: Path, dry_run: bool) -> Dict[str, bool]:
    """Met la base au niveau ; rend l'etat final des colonnes et tables."""
    versions = asyncio.run(_versions_alembic(core))
    if versions:
        if dry_run:
            print(f" [2/4] (dry-run) base suivie ({', '.join(versions)}) : alembic upgrade head")
        else:
            print(f" [2/4] base suivie ({', '.join(versions)}) : alembic upgrade head...")
            command.upgrade(Config(str(alembic_ini)), "head")
        return asyncio.run(_etat(core))

    print(
        " [2/4] base non suivie par alembic (tables creees par le seed) : DDL direct, "
        "pas d'upgrade, qui rejouerait toutes les migrations."
    )
    etat = asyncio.run(_etat(core))
    manquants = [nom for nom, present in etat.items() if not present]
    if not manquants:
        print("        tout est deja en place")
        return etat
    if dry_run:
        print(f"        (dry-run) creerait : {', '.join(manquants)}")
        return etat
    asyncio.run(_ddl_direct(core))
    print(f"        crees : {', '.join(manquants)}")
    return asyncio.run(_etat(core))


# -- 3. Datasets -------------------------------------------------------------------


async def regler_datasets(
    core: str, dataset_ids: List[int], pages: int, dry_run: bool, colonne: bool
) -> None:
    from sqlalchemy import text

    # En dry-run sur une base qui n'a pas encore la colonne, on ne peut pas la
    # lire : on montre les datasets vises, valeur actuelle inconnue (NULL).
    valeur = "expected_page_count" if colonne else "NULL"
    filtre_vide = "AND expected_page_count IS NULL" if colonne else ""
    engine = _engine(core)
    try:
        async with engine.begin() as conn:
            if dataset_ids:
                requete = (
                    f"SELECT id, name, {valeur} AS actuel FROM dataset "
                    "WHERE id = ANY(:ids) ORDER BY id"
                )
                cibles = (await conn.execute(text(requete), {"ids": dataset_ids})).all()
            else:
                requete = (
                    f"SELECT id, name, {valeur} AS actuel FROM dataset "
                    f"WHERE name = :name {filtre_vide} ORDER BY id"
                )
                cibles = (await conn.execute(text(requete), {"name": CERFA_DATASET_NAME})).all()

            if not cibles:
                tous = (await conn.execute(text("SELECT id, name FROM dataset ORDER BY id"))).all()
                print(" [3/4] aucun dataset a regler. Datasets presents :")
                for ligne in tous:
                    print(f"        id={ligne.id}  {ligne.name}")
                print("        relancer avec --dataset-id <id> pour en viser un.")
                return

            for ligne in cibles:
                action = "(dry-run) reglerait" if dry_run else "regle"
                print(
                    f" [3/4] {action} dataset id={ligne.id} {ligne.name} : "
                    f"{ligne.actuel} -> {pages} pages"
                )
            if not dry_run:
                await conn.execute(
                    text("UPDATE dataset SET expected_page_count = :pages WHERE id = ANY(:ids)"),
                    {"pages": pages, "ids": [ligne.id for ligne in cibles]},
                )
    finally:
        await engine.dispose()


# -- 4. Schemas CERFA ----------------------------------------------------------------


def _donnees_cerfa(core: str) -> Tuple[Dict[int, str], Dict[str, str]]:
    """(page -> description, cle semantique -> description du champ)."""
    cerfa = importlib.import_module(f"{core}.schemas.cerfa_v2")
    descriptions = {
        cle: str(spec.get("description") or "")
        for champs in cerfa.CERFA_V2_PAGE_FIELDS.values()
        for cle, spec in champs.items()
    }
    return dict(cerfa.CERFA_V2_PAGE_TITLES), descriptions


def _cle_semantique(section_id: Optional[str], field_key: str) -> str:
    """Meme regle que merger.semantic_key, sans importer le worker."""
    if not section_id or field_key.startswith(f"{section_id}."):
        return field_key
    return f"{section_id}.{field_key}"


async def decrire_schemas_cerfa(core: str, dry_run: bool, etat: Dict[str, bool]) -> None:
    """Decrit les pages des schemas CERFA et complete la description des champs.

    Seuls les manques sont combles : une page deja decrite et une description
    deja saisie ne sont pas reecrites.
    """
    from sqlalchemy import text

    if not (etat.get("schema_page") and etat.get("description")):
        print(" [4/4] (dry-run) schema_page pas encore creee : pages et descriptions apres")
        return

    pages, descriptions = _donnees_cerfa(core)
    engine = _engine(core)
    try:
        async with engine.begin() as conn:
            schemas = (
                await conn.execute(
                    text("SELECT id, name FROM doc_schema WHERE document_type = :t ORDER BY id"),
                    {"t": CERFA_DOCUMENT_TYPE},
                )
            ).all()
            if not schemas:
                print(f" [4/4] aucun schema {CERFA_DOCUMENT_TYPE} en base, rien a decrire")
                return
            for schema in schemas:
                decrites = {
                    r[0]
                    for r in await conn.execute(
                        text("SELECT page_number FROM schema_page WHERE schema_id = :s"),
                        {"s": schema.id},
                    )
                }
                pages_a_ecrire = {n: d for n, d in pages.items() if n not in decrites}

                specs = (
                    await conn.execute(
                        text(
                            "SELECT id, section_id, field_key FROM field_spec "
                            "WHERE schema_id = :s AND (description IS NULL OR description = '')"
                        ),
                        {"s": schema.id},
                    )
                ).all()
                a_decrire = [
                    {"id": spec.id, "d": descriptions[cle]}
                    for spec in specs
                    if descriptions.get(cle := _cle_semantique(spec.section_id, spec.field_key))
                ]

                action = "(dry-run) ecrirait" if dry_run else "ecrit"
                print(
                    f" [4/4] schema id={schema.id} {schema.name} : {action} "
                    f"{len(pages_a_ecrire)} page(s), {len(a_decrire)} description(s) de champ"
                )
                if dry_run:
                    continue
                for numero, description in sorted(pages_a_ecrire.items()):
                    await conn.execute(
                        text(
                            "INSERT INTO schema_page (schema_id, page_number, description) "
                            "VALUES (:s, :n, :d) ON CONFLICT DO NOTHING"
                        ),
                        {"s": schema.id, "n": numero, "d": description},
                    )
                if a_decrire:
                    await conn.execute(
                        text("UPDATE field_spec SET description = :d WHERE id = :id"),
                        a_decrire,
                    )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("Etapes")[0])
    parser.add_argument("--dry-run", action="store_true", help="Montre sans rien ecrire")
    parser.add_argument(
        "--fichier-seul",
        action="store_true",
        help="Cree seulement les fichiers de migration, sans toucher a la base",
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
    creer_migrations(alembic_ini, args.dry_run)
    if args.fichier_seul:
        return
    etat = mettre_au_niveau(core, alembic_ini, args.dry_run)
    asyncio.run(
        regler_datasets(
            core, args.dataset_id, args.pages, args.dry_run, etat["expected_page_count"]
        )
    )
    asyncio.run(decrire_schemas_cerfa(core, args.dry_run, etat))


if __name__ == "__main__":
    main()
