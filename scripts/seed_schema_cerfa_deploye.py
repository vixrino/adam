"""
scripts/seed_schema_cerfa_deploye.py
------------------------------------
Pose le schema CERFA surendettement (13594*02) dans un projet d'une base
DEJA EN SERVICE : un projet, son DOC_SCHEMA, ses SCHEMA_PAGE et ses FIELD_SPEC.
Ni utilisateur, ni affectation, ni lot, ni document.

Pourquoi un script de plus
--------------------------
seed.py vide les tables avec --reset et cree des organisations et des agents
fictifs. seed_schema_cerfa.py ne cree que le schema, mais il cree aussi
l'organisation si son slug est inconnu, appelle create_all et sait remplacer
(donc supprimer) un schema. Sur une base partagee, une faute de frappe dans le
slug ou un --replace de trop sont des erreurs qu'on ne rattrape pas. Ce script
reprend la meme source des champs (build_specs, build_pages de
seed_schema_cerfa.py) avec des garde-fous :

  - l'organisation doit exister : sinon il s'arrete et liste les slugs connus ;
  - il ne remplace rien : un schema CERFA deja present dans le projet l'arrete ;
  - il n'appelle ni create_all ni TRUNCATE : il verifie que la base a les tables
    et colonnes attendues, et sinon s'arrete avant d'ecrire ;
  - il affiche la destination (hote, base, schema ; jamais le mot de passe) et
    demande confirmation, sauf avec --yes ;
  - tout tient en une transaction : une erreur n'en laisse rien.

Le projet est cree sans membre. Un administrateur NOTA le voit (son role
neutralise le filtrage par organisation) et y affecte ensuite l'administrateur
metier depuis la fenetre des membres.

Usage (depuis la racine du depot, ou se trouve le .env de la base visee) :
    python scripts/seed_schema_cerfa_deploye.py --organisation-slug bdf --dry-run
    python scripts/seed_schema_cerfa_deploye.py --organisation-slug bdf
    python scripts/seed_schema_cerfa_deploye.py --organisation-slug bdf \\
        --project-name "Surendettement - DIRES Nord" --yes
"""

import argparse
import asyncio
from pathlib import Path
import sys
from typing import List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from seed_schema_cerfa import (
    DOCUMENT_TYPE,
    PROJECT_DESCRIPTION,
    SCHEMA_NAME,
    SCHEMA_VERSION,
    build_pages,
    build_specs,
)
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from adam_core.core.config import CoreSettings
from adam_core.db.base import SCHEMA_NAME as DB_SCHEMA
from adam_core.db.session import get_engine, init_engine
from adam_core.enums.status import ProjectStatus
from adam_core.models import DocSchema, FieldSpec, Organisation, Project

settings = CoreSettings()
SEPARATOR = "-" * 70

#: Meme libelle que le projet type de seed.py.
DEFAULT_PROJECT_NAME = "Traitement des declarations de surendettement"

#: Ce que l'insertion suppose : une base creee avant ces colonnes les n'a pas, et
#: create_all n'ajoute jamais une colonne a une table existante.
REQUIRED_COLUMNS: Set[Tuple[str, str]] = {
    ("organisation", "slug"),
    ("project", "organisation_id"),
    ("doc_schema", "locked"),
    ("doc_schema", "specimen_file_id"),
    ("field_spec", "description"),
    ("field_spec", "sensitive"),
    ("schema_page", "page_number"),
}


def destination() -> str:
    """Base visee, sans le mot de passe."""
    url = make_url(settings.async_database_url)
    return f"{url.host}:{url.port}/{url.database}  schema={DB_SCHEMA}  utilisateur={url.username}"


async def verifier_base(session: AsyncSession) -> None:
    """S'arrete si une table ou colonne attendue manque : la base n'est pas au niveau du code."""
    rows = await session.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = :schema"
        ),
        {"schema": DB_SCHEMA},
    )
    presentes = {tuple(row) for row in rows}
    manquantes = sorted(REQUIRED_COLUMNS - presentes)
    if manquantes:
        detail = "\n".join(f"      {table}.{column}" for table, column in manquantes)
        raise SystemExit(
            f"\n  La base n'est pas au niveau du code : il manque, dans le schema {DB_SCHEMA},\n"
            f"{detail}\n  Rien n'a ete ecrit."
        )


async def trouver_organisation(session: AsyncSession, slug: str) -> Organisation:
    org = (
        await session.execute(select(Organisation).where(Organisation.slug == slug))
    ).scalar_one_or_none()
    if org is None:
        slugs = (await session.execute(select(Organisation.slug).order_by(Organisation.slug))).all()
        connus = ", ".join(s for (s,) in slugs) or "(aucune)"
        raise SystemExit(
            f"\n  Organisation '{slug}' introuvable. Slugs existants : {connus}\n"
            f"  Rien n'a ete ecrit."
        )
    return org


async def schema_existant(session: AsyncSession, project_id: int) -> Optional[DocSchema]:
    return (
        await session.execute(
            select(DocSchema)
            .where(DocSchema.project_id == project_id)
            .where(DocSchema.document_type == DOCUMENT_TYPE)
        )
    ).scalar_one_or_none()


def confirmer(yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        raise SystemExit("\n  Pas de terminal pour confirmer : relancer avec --yes.")
    return input("\n  Ecrire dans cette base ? [o/N] ").strip().lower() in {"o", "oui", "y", "yes"}


async def poser_schema(session: AsyncSession, project: Project) -> Tuple[DocSchema, int, int]:
    schema = DocSchema(
        project_id=project.id,
        version=SCHEMA_VERSION,
        name=SCHEMA_NAME,
        document_type=DOCUMENT_TYPE,
    )
    session.add(schema)
    await session.flush()

    specs = build_specs()
    session.add_all(
        FieldSpec(
            schema_id=schema.id,
            page=spec["page"],
            section_id=spec["section_id"],
            section_label=spec["section_label"],
            group_id=spec["group_id"],
            field_key=spec["field_key"],
            display_label=spec["display_label"],
            description=spec["description"],
            value_type=spec["value_type"],
            required=spec["required"],
            sensitive=spec["sensitive"],
            display_order=spec["display_order"],
        )
        for spec in specs
    )
    pages = build_pages(schema.id)
    session.add_all(pages)
    await session.flush()
    return schema, len(specs), len(pages)


async def main(organisation_slug: str, project_name: str, dry_run: bool, yes: bool) -> None:
    print(SEPARATOR)
    print(f"  Destination : {destination()}")
    print(f"  Organisation : {organisation_slug}")
    print(f"  Projet       : {project_name}")
    print(SEPARATOR)

    init_engine(settings.async_database_url, echo=False)
    factory = async_sessionmaker(bind=get_engine(), expire_on_commit=False)
    try:
        async with factory() as session:
            await verifier_base(session)
            org = await trouver_organisation(session, organisation_slug)
            project = (
                await session.execute(
                    select(Project)
                    .where(Project.organisation_id == org.id)
                    .where(Project.name == project_name)
                )
            ).scalar_one_or_none()
            if project is not None:
                existant = await schema_existant(session, project.id)
                if existant is not None:
                    raise SystemExit(
                        f"\n  Le projet existe deja et porte un schema {DOCUMENT_TYPE} "
                        f"(id={existant.id}). Rien n'est remplace. Rien n'a ete ecrit."
                    )

            plan: List[str] = [
                f"organisation existante : {org.name} (id={org.id})",
                (
                    f"projet existant : {project.name} (id={project.id}), sans schema CERFA"
                    if project is not None
                    else f"projet a creer : {project_name}"
                ),
                f"schema a creer : {SCHEMA_NAME} (version {SCHEMA_VERSION})",
                f"{len(build_specs())} champs, {len(build_pages(0))} pages",
                "aucun utilisateur, aucune affectation, aucun lot, aucun document",
            ]
            for ligne in plan:
                print(f"  - {ligne}")

            if dry_run:
                print("\n  --dry-run : rien n'a ete ecrit.")
                return
            if not confirmer(yes):
                print("\n  Annule. Rien n'a ete ecrit.")
                return

            if project is None:
                project = Project(
                    organisation_id=org.id,
                    name=project_name,
                    description=PROJECT_DESCRIPTION,
                    status=ProjectStatus.ACTIVE.value,
                )
                session.add(project)
                await session.flush()
            schema, n_champs, n_pages = await poser_schema(session, project)
            await session.commit()
            print(
                f"\n  Fait : projet id={project.id}, schema id={schema.id}, "
                f"{n_champs} champs, {n_pages} pages."
            )
    finally:
        await get_engine().dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pose le schema CERFA dans une base en service")
    parser.add_argument(
        "--organisation-slug",
        required=True,
        help="Slug d'une organisation EXISTANTE (jamais creee par ce script)",
    )
    parser.add_argument("--project-name", default=DEFAULT_PROJECT_NAME)
    parser.add_argument(
        "--dry-run", action="store_true", help="Verifie et affiche le plan, n'ecrit rien"
    )
    parser.add_argument("--yes", action="store_true", help="Ne demande pas de confirmation")
    args = parser.parse_args()
    asyncio.run(main(args.organisation_slug, args.project_name, args.dry_run, args.yes))
    print(SEPARATOR)
