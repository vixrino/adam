"""
scripts/seed_schema_cerfa.py
----------------------------
Cree un DOC_SCHEMA complet pour le CERFA surendettement (n° 13594*02), avec
ses FIELD_SPEC, dans un projet dedie.

Pourquoi ce script en plus de seed.py
--------------------------------------
seed.py monte un jeu de demonstration de bout en bout : organisation, users,
projet, schema, dataset, document, resultat OCR et champs annotes. C'est ce
qu'il faut pour derouler le parcours complet, mais c'est trop pour montrer un
schema : il faut alors relire des documents et des valeurs OCR fictives qui
n'ont rien a voir avec la structure du formulaire.

Ce script s'arrete au schema. Il produit ce qu'un administrateur metier
verrait apres avoir declare un type de document : la liste des champs
attendus, page par page, section par section, avec leurs types. Rien de plus.

Champs repetables
-----------------
Le CERFA ouvre plusieurs emplacements identiques pour un meme objet : six
prets a la consommation page 10, plusieurs dettes page 6, plusieurs personnes
au domicile page 2. cerfa_v2.py, qui pilote l'appel OCR, les aplatit
volontairement en une seule instance : la repetition ne change rien a ce qu'on
demande a Mistral, seulement au depliage de sa reponse.

Ici, au contraire, la repetition doit exister : un operateur qui annote le
pret n° 3 doit avoir des champs distincts de ceux du pret n° 1. C'est le role
de FieldSpec.group_id, et de la contrainte d'unicite
(schema_id, section_id, group_id, field_key) qui l'accompagne : le meme
field_key peut se repeter dans une section a condition de porter un group_id
different.

REPEATABLE_SECTIONS ci-dessous declare, pour chaque section repetable, le
nombre d'emplacements du formulaire papier. C'est la seule chose a modifier si
un CERFA ulterieur en ouvre davantage.

Usage :
    python scripts/seed_schema_cerfa.py
    python scripts/seed_schema_cerfa.py --list          # sans base, juste l'apercu
    python scripts/seed_schema_cerfa.py --replace       # remplace un schema deja present
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from adam_core.core.config import CoreSettings
from adam_core.db.session import create_tables, get_engine, init_engine
from adam_core.enums.status import FieldValueType, ProjectStatus
from adam_core.models import DocSchema, FieldSpec, Organisation, Project
from adam_core.schemas.cerfa_v2 import CERFA_V2_PAGE_FIELDS

settings = CoreSettings()
SEPARATOR = "-" * 70

ORGANISATION_NAME = "Banque de France"
ORGANISATION_SLUG = "bdf"
PROJECT_NAME = "Surendettement - demonstration"
PROJECT_DESCRIPTION = "Annotation des declarations de surendettement (CERFA 13594*02)"
SCHEMA_NAME = "Declaration de surendettement (CERFA 13594*02)"
DOCUMENT_TYPE = "CERFA_SURENDETTEMENT_V2"
SCHEMA_VERSION = 2

#: Libelle lisible de chaque section, l'identifiant technique venant du prefixe
#: du field_key. Une section absente de cette table retombe sur son identifiant.
SECTION_LABELS: Dict[str, str] = {
    "deposant": "Deposant",
    "co_deposant": "Co-deposant",
    "coordonnees_personnelles": "Coordonnees personnelles",
    "assist_travailleur_social": "Assistance par un travailleur social",
    "certification": "Certification et signatures",
    "dossier_precedent": "Dossier precedent",
    "situation_familiale": "Situation familiale",
    "personnes_a_charge": "Personnes vivant au domicile",
    "situation_logement_deposant": "Situation de logement",
    "dettes_logement": "Dettes de logement",
    "dettes_courantes": "Dettes de charges courantes",
    "credits_consommation": "Credits a la consommation",
}

#: Sections repetables : (nombre d'emplacements, prefixe de group_id, libelle
#: de l'instance). Les valeurs suivent le nombre de cases du formulaire papier.
REPEATABLE_SECTIONS: Dict[str, Tuple[int, str, str]] = {
    "personnes_a_charge": (5, "personne", "Personne n° {n}"),
    "dettes_logement": (4, "dette_logement", "Dette n° {n}"),
    "dettes_courantes": (5, "dette_courante", "Dette n° {n}"),
    "credits_consommation": (6, "pret", "Pret n° {n}"),
}

#: Champs porteurs de donnee personnelle sensible, reconnus par leur suffixe.
#: Pilote is_sensitive, qui determine si comparison_result stocke la valeur en
#: clair ou son HMAC.
_SENSITIVE_SUFFIXES = (
    "nom_naissance",
    "nom_usage",
    "prenoms",
    "date_naissance",
    "lieu_naissance",
)


def _value_type(field_def: Mapping[str, Any]) -> str:
    """Traduit le type JSON Schema de cerfa_schema en FieldValueType.

    Un `string` avec `format: date` devient DATE : c'est la seule information
    de format que porte le schema d'origine, et la perdre obligerait
    l'operateur a ressaisir des dates en texte libre.
    """
    json_type = field_def.get("type", "string")
    if json_type == "boolean":
        return FieldValueType.BOOLEAN.value
    if json_type == "number":
        return FieldValueType.NUMBER.value
    if json_type == "string" and field_def.get("format") == "date":
        return FieldValueType.DATE.value
    return FieldValueType.TEXT.value


def _is_sensitive(field_key: str) -> bool:
    return field_key.endswith(_SENSITIVE_SUFFIXES)


def build_specs() -> List[Dict[str, Any]]:
    """Deplie CERFA_V2_PAGE_FIELDS en une liste de FieldSpec a creer.

    Une section repetable produit N fois ses champs, un group_id par instance.
    Une section simple les produit une fois, group_id a None — c'est la valeur
    qui distingue "champ unique" de "premiere instance d'un groupe", et non un
    group_id conventionnel comme "1", qui obligerait chaque lecteur a savoir
    que 1 signifie parfois "unique".
    """
    specs: List[Dict[str, Any]] = []
    order = 0

    for page in sorted(CERFA_V2_PAGE_FIELDS):
        fields = CERFA_V2_PAGE_FIELDS[page]

        # Regroupe par section en preservant l'ordre de declaration, qui suit
        # l'ordre de lecture du formulaire.
        by_section: Dict[str, List[Tuple[str, Mapping[str, Any]]]] = {}
        for full_key, field_def in fields.items():
            section_id, _, field_key = full_key.partition(".")
            by_section.setdefault(section_id, []).append((field_key, field_def))

        for section_id, section_fields in by_section.items():
            section_label = SECTION_LABELS.get(section_id, section_id)
            repeat = REPEATABLE_SECTIONS.get(section_id)
            instances: List[Tuple[Optional[str], str]]
            if repeat is None:
                instances = [(None, "")]
            else:
                count, prefix, instance_label = repeat
                instances = [
                    (f"{prefix}_{n}", instance_label.format(n=n)) for n in range(1, count + 1)
                ]

            for group_id, instance_label in instances:
                for field_key, field_def in section_fields:
                    label = field_def.get("description", field_key)
                    specs.append(
                        {
                            "page": page,
                            "section_id": section_id,
                            "section_label": section_label,
                            "group_id": group_id,
                            "field_key": field_key,
                            "display_label": (
                                f"{label} - {instance_label}" if instance_label else label
                            ),
                            "value_type": _value_type(field_def),
                            "required": False,
                            "is_sensitive": _is_sensitive(field_key),
                            "display_order": order,
                        }
                    )
                    order += 1

    return specs


def print_overview(specs: List[Dict[str, Any]]) -> None:
    """Apercu page par page, sans toucher a la base."""
    current: Tuple[Any, ...] = ()
    for spec in specs:
        header = (spec["page"], spec["section_id"], spec["group_id"])
        if header != current:
            current = header
            group = f"  [{spec['group_id']}]" if spec["group_id"] else ""
            print(f"\n  page {spec['page']} - {spec['section_label']}{group}")
        print(f"      {spec['field_key']:<28} {spec['value_type']:<8} {spec['display_label']}")


async def _get_or_create_project(session: AsyncSession) -> Project:
    """Organisation et projet d'accueil, crees si absents.

    Le script est rejouable : relance apres relance, il retrouve le meme projet
    au lieu d'en empiler des copies.
    """
    org = (
        await session.execute(select(Organisation).where(Organisation.slug == ORGANISATION_SLUG))
    ).scalar_one_or_none()
    if org is None:
        org = Organisation(name=ORGANISATION_NAME, slug=ORGANISATION_SLUG)
        session.add(org)
        await session.flush()
        print(f"  organisation creee : {org.name}")
    else:
        print(f"  organisation existante : {org.name}")

    project = (
        await session.execute(
            select(Project)
            .where(Project.organisation_id == org.id)
            .where(Project.name == PROJECT_NAME)
        )
    ).scalar_one_or_none()
    if project is None:
        project = Project(
            organisation_id=org.id,
            name=PROJECT_NAME,
            description=PROJECT_DESCRIPTION,
            status=ProjectStatus.ACTIVE.value,
        )
        session.add(project)
        await session.flush()
        print(f"  projet cree : {project.name} (id={project.id})")
    else:
        print(f"  projet existant : {project.name} (id={project.id})")

    return project


async def seed_schema(session: AsyncSession, replace: bool) -> DocSchema:
    project = await _get_or_create_project(session)

    existing = (
        await session.execute(
            select(DocSchema)
            .where(DocSchema.project_id == project.id)
            .where(DocSchema.document_type == DOCUMENT_TYPE)
        )
    ).scalar_one_or_none()

    if existing is not None:
        if not replace:
            raise SystemExit(
                f"\n  Un schema {DOCUMENT_TYPE} existe deja dans ce projet (id={existing.id}).\n"
                f"  Relancer avec --replace pour le remplacer, ou le supprimer depuis l'API."
            )
        # La cascade sur field_spec.schema_id emporte les champs avec le schema.
        await session.delete(existing)
        await session.flush()
        print(f"  schema precedent supprime (id={existing.id})")

    schema = DocSchema(
        project_id=project.id,
        version=SCHEMA_VERSION,
        name=SCHEMA_NAME,
        document_type=DOCUMENT_TYPE,
    )
    session.add(schema)
    await session.flush()
    print(f"  schema cree : {schema.name} (id={schema.id})")

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
            value_type=spec["value_type"],
            required=spec["required"],
            is_sensitive=spec["is_sensitive"],
            display_order=spec["display_order"],
        )
        for spec in specs
    )
    await session.flush()

    grouped = sum(1 for spec in specs if spec["group_id"] is not None)
    print(f"  {len(specs)} champs crees, dont {grouped} dans une section repetable")
    for section_id, (count, prefix, _) in REPEATABLE_SECTIONS.items():
        per_instance = sum(1 for spec in specs if spec["section_id"] == section_id) // count
        print(
            f"      {SECTION_LABELS.get(section_id, section_id)} : "
            f"{count} instances ({prefix}_1 a {prefix}_{count}), "
            f"{per_instance} champs chacune"
        )

    return schema


async def main(replace: bool) -> None:
    init_engine(settings.async_database_url, echo=False)
    await create_tables()
    factory = async_sessionmaker(bind=get_engine(), expire_on_commit=False)
    async with factory() as session:
        await seed_schema(session, replace=replace)
        await session.commit()
    await get_engine().dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cree le schema CERFA surendettement")
    parser.add_argument(
        "--list",
        action="store_true",
        help="Affiche les champs qui seraient crees, sans toucher a la base",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Remplace le schema s'il existe deja dans le projet",
    )
    args = parser.parse_args()

    all_specs = build_specs()

    print(SEPARATOR)
    print(f"{SCHEMA_NAME}")
    print(
        f"  {len(CERFA_V2_PAGE_FIELDS)} pages decrites, {len(all_specs)} champs, "
        f"{len(REPEATABLE_SECTIONS)} sections repetables"
    )
    print(SEPARATOR)

    if args.list:
        print_overview(all_specs)
        print(f"\n{SEPARATOR}")
        sys.exit(0)

    asyncio.run(main(replace=args.replace))
    print(SEPARATOR)
    print("Schema pret. Il apparait dans le projet, onglet Schemas.")
    print(SEPARATOR)
