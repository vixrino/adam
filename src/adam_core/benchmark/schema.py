"""Le schema d'un dataset tel que le benchmark le lit, et son empreinte.

Partage par le worker (qui extrait et compare) et par l'API (qui fige un
export de dataset avec l'empreinte du schema du moment).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_core.models import DocSchema, FieldSpec, SchemaPage


async def schema_en_dict(db: AsyncSession, schema_id: int) -> Dict[str, Any]:
    """Le schema sous la forme de GET /schemas/{id}, pour ModeleDocument."""
    nom = (await db.execute(select(DocSchema.name).where(DocSchema.id == schema_id))).scalar_one()
    pages = (
        await db.execute(
            select(SchemaPage.page_number, SchemaPage.description)
            .where(SchemaPage.schema_id == schema_id)
            .order_by(SchemaPage.page_number)
        )
    ).all()
    specs = (
        (
            await db.execute(
                select(FieldSpec)
                .where(FieldSpec.schema_id == schema_id)
                .order_by(FieldSpec.page, FieldSpec.display_order, FieldSpec.id)
            )
        )
        .scalars()
        .all()
    )
    return {
        "name": nom,
        "pages": [{"page_number": n, "description": d} for n, d in pages],
        "field_specs": [
            {
                "id": fs.id,
                "page": fs.page,
                "section_id": fs.section_id,
                "field_key": fs.field_key,
                "group_id": fs.group_id,
                "display_label": fs.display_label,
                "description": fs.description,
                "value_type": fs.value_type,
                "polygon": fs.polygon,
            }
            for fs in specs
        ],
    }


def empreinte_schema(schema: Mapping[str, Any]) -> str:
    """Empreinte du schema tel qu'il pilote l'extraction et la comparaison.

    Faite du contenu, pas des ids : le meme schema en base de dev et en base de
    recette a la meme empreinte, et un champ ajoute, retype ou redecrit la
    change. Les polygones, qui ne jouent ni sur la lecture ni sur le verdict,
    n'y entrent pas.
    """
    contenu = {
        "pages": sorted((p["page_number"], p["description"]) for p in schema.get("pages") or []),
        "champs": sorted(
            (
                s["page"],
                s.get("section_id") or "",
                s["field_key"],
                s.get("group_id") or "",
                s.get("value_type") or "",
                s.get("description") or s.get("display_label") or "",
            )
            for s in schema.get("field_specs") or []
        ),
    }
    return hashlib.sha256(json.dumps(contenu, ensure_ascii=False).encode()).hexdigest()[:16]
