"""
scripts/seed_schema_from_json.py
---------------------------------
Cree (ou remplace) un DOC_SCHEMA et ses FIELD_SPEC a partir d'un fichier JSON.

Boucle d'edition visee :
  1. Ecrire le JSON des champs (field_key, display_label, description, type,
     section, ...), polygon absent ou null.
  2. python scripts/seed_schema_from_json.py mon_schema.json
  3. Dessiner les zones dans l'IHM du schema (chaque trace fait un PATCH
     /schemas/{id}/field-specs/{id} qui remplit polygon).
  4. python scripts/export_schema_seed.py <schema_id> -o mon_schema.json
     reecrit le meme fichier, polygon rempli : seed complet et rejouable
     ailleurs via ce script.

Format JSON attendu :
{
  "organisation_slug": "dgrh",
  "project_name": "Mon projet",
  "project_description": "optionnel",
  "schema_name": "Mon schema",
  "document_type": "MON_TYPE_V1",
  "version": 1,
  "fields": [
    {
      "section_id": "deposant",
      "section_label": "Deposant",
      "field_key": "deposant.nom",
      "display_label": "Nom",
      "value_type": "TEXT",
      "required": true,
      "sensitive": false,
      "description": "Nom de famille du deposant",
      "page": 1,
      "group_id": null,
      "polygon": null
    }
  ]
}

display_order est deduit de la position dans la liste "fields".
L'organisation doit deja exister (on ne cree pas d'organisation depuis un
seed) ; le projet est cree s'il n'existe pas encore dans cette organisation.

Usage :
    python scripts/seed_schema_from_json.py mon_schema.json
    python scripts/seed_schema_from_json.py mon_schema.json --replace
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_core.core.config import CoreSettings
from adam_core.db.session import get_async_session, init_engine
from adam_core.enums.status import ProjectStatus
from adam_core.models import DocSchema, FieldSpec, Organisation, Project

settings = CoreSettings()


async def _get_or_create_project(session: AsyncSession, data: Dict[str, Any]) -> Project:
    org = (
        await session.execute(
            select(Organisation).where(Organisation.slug == data["organisation_slug"])
        )
    ).scalar_one_or_none()
    if org is None:
        raise SystemExit(
            f"Organisation '{data['organisation_slug']}' introuvable. "
            "Ce script ne cree pas d'organisation : verifiez le slug."
        )

    project = (
        await session.execute(
            select(Project)
            .where(Project.organisation_id == org.id)
            .where(Project.name == data["project_name"])
        )
    ).scalar_one_or_none()
    if project is None:
        project = Project(
            organisation_id=org.id,
            name=data["project_name"],
            description=data.get("project_description", ""),
            status=ProjectStatus.ACTIVE.value,
        )
        session.add(project)
        await session.flush()
        print(f"  projet cree : {project.name} (id={project.id})")
    else:
        print(f"  projet existant : {project.name} (id={project.id})")

    return project


async def seed_schema(session: AsyncSession, data: Dict[str, Any], replace: bool) -> DocSchema:
    project = await _get_or_create_project(session, data)

    existing = (
        await session.execute(
            select(DocSchema)
            .where(DocSchema.project_id == project.id)
            .where(DocSchema.document_type == data["document_type"])
        )
    ).scalar_one_or_none()

    if existing is not None:
        if not replace:
            raise SystemExit(
                f"Un schema {data['document_type']} existe deja dans ce projet "
                f"(id={existing.id}). Relancer avec --replace pour le remplacer."
            )
        await session.delete(existing)  # cascade sur field_spec.schema_id
        await session.flush()
        print(f"  schema precedent supprime (id={existing.id})")

    schema = DocSchema(
        project_id=project.id,
        version=data.get("version", 1),
        name=data["schema_name"],
        document_type=data["document_type"],
    )
    session.add(schema)
    await session.flush()
    print(f"  schema cree : {schema.name} (id={schema.id})")

    fields = data["fields"]
    session.add_all(
        FieldSpec(
            schema_id=schema.id,
            page=field["page"],
            section_id=field["section_id"],
            section_label=field["section_label"],
            group_id=field.get("group_id"),
            field_key=field["field_key"],
            display_label=field["display_label"],
            value_type=field.get("value_type", "TEXT"),
            required=field.get("required", False),
            sensitive=field.get("sensitive", False),
            description=field.get("description"),
            display_order=i,
            polygon=field.get("polygon"),
        )
        for i, field in enumerate(fields)
    )
    await session.flush()
    print(f"  {len(fields)} champs crees")

    return schema


async def main(json_path: Path, replace: bool) -> None:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    init_engine(settings.async_database_url, echo=False)
    async with get_async_session() as session:
        schema = await seed_schema(session, data, replace=replace)
        await session.commit()
        print(f"\nOK. schema_id={schema.id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed un schema depuis un JSON de champs")
    parser.add_argument("json_file", type=Path)
    parser.add_argument("--replace", action="store_true", help="Remplace le schema existant")
    args = parser.parse_args()
    asyncio.run(main(args.json_file, replace=args.replace))
