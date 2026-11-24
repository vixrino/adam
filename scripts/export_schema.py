"""
scripts/export_schema_seed.py
-------------------------------
Exporte un DOC_SCHEMA (et ses FIELD_SPEC, zones comprises) vers le meme
format JSON que seed_schema_from_json.py attend en entree.

Etape 4 de la boucle decrite dans seed_schema_from_json.py : une fois les
zones dessinees dans l'IHM, ce script relit la base et ecrit un seed complet,
rejouable ailleurs avec seed_schema_from_json.py.

Usage :
    python scripts/export_schema_seed.py <schema_id>
    python scripts/export_schema_seed.py <schema_id> -o mon_schema.json
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from adam_core.core.config import CoreSettings
from adam_core.db.session import get_async_session, init_engine
from adam_core.models import DocSchema, Organisation, Project

settings = CoreSettings()


async def export_schema(session: AsyncSession, schema_id: int) -> dict:
    schema = (
        await session.execute(
            select(DocSchema)
            .where(DocSchema.id == schema_id)
            .options(selectinload(DocSchema.field_specs))
        )
    ).scalar_one_or_none()
    if schema is None:
        raise SystemExit(f"Schema {schema_id} introuvable.")

    project = await session.get(Project, schema.project_id)
    org = await session.get(Organisation, project.organisation_id) if project else None

    fields = [
        {
            "section_id": fs.section_id,
            "section_label": fs.section_label,
            "field_key": fs.field_key,
            "display_label": fs.display_label,
            "value_type": fs.value_type,
            "required": fs.required,
            "sensitive": fs.sensitive,
            "description": fs.description,
            "page": fs.page,
            "group_id": fs.group_id,
            "polygon": fs.polygon,
        }
        for fs in sorted(schema.field_specs, key=lambda x: (x.page, x.display_order))
    ]
    missing_polygon = sum(1 for f in fields if f["polygon"] is None)
    if missing_polygon:
        print(f"  attention : {missing_polygon}/{len(fields)} champs sans zone dessinee")

    return {
        "organisation_slug": org.slug if org else None,
        "project_name": project.name if project else None,
        "schema_name": schema.name,
        "document_type": schema.document_type,
        "version": schema.version,
        "fields": fields,
    }


async def main(schema_id: int, out_path: Path) -> None:
    init_engine(settings.async_database_url, echo=False)
    async with get_async_session() as session:
        data = await export_schema(session, schema_id)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK. {len(data['fields'])} champs ecrits dans {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Exporte un schema+field_specs en JSON")
    parser.add_argument("schema_id", type=int)
    parser.add_argument("-o", "--out", type=Path, default=Path("schema_export.json"))
    args = parser.parse_args()
    asyncio.run(main(args.schema_id, args.out))
