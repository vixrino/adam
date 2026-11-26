"""
scripts/verifier_schema.py
--------------------------
Montre ce que l'extraction OCR lira d'un schema : ses pages decrites et ses
champs, avec la part qui porte une description. Lecture seule, directement en
base : ni API a lancer ni authentification.

Le paquet *_core (nota_core ou adam_core) est trouve sous src/ : le script
tourne tel quel dans les deux depots. Il se lance depuis la racine du depot,
la ou se trouve le .env.

Usage :
    python scripts/verifier_schema.py                 # schemas CERFA
    python scripts/verifier_schema.py --schema-id 5
    python scripts/verifier_schema.py --tous          # tous les schemas
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import sys
from pathlib import Path
from typing import Any, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

CERFA_DOCUMENT_TYPE = "CERFA_SURENDETTEMENT_V2"


def _paquet_core() -> str:
    trouves = sorted(p.name for p in SRC.glob("*_core") if (p / "core" / "config.py").is_file())
    if len(trouves) != 1:
        raise SystemExit(f"attendu un seul src/*_core, trouve : {trouves}")
    return trouves[0]


async def verifier(core: str, schema_id: Optional[int], tous: bool) -> None:
    # Requetes construites sur les modeles, pas en SQL ecrit a la main : dans
    # nota, les tables vivent dans le schema PostgreSQL « nota » (MetaData de
    # nota_core.db.base). Un « FROM doc_schema » non qualifie suit le
    # search_path et lit public.doc_schema, une table residuelle qui peut
    # exister a cote et ne montre pas les schemas de l'application.
    settings = importlib.import_module(f"{core}.core.config").get_core_settings()
    models = importlib.import_module(f"{core}.models")
    doc_schema = models.DocSchema.__table__
    schema_page = models.SchemaPage.__table__
    field_spec = models.FieldSpec.__table__
    print(f"tables lues : {doc_schema.fullname}, {schema_page.fullname}, {field_spec.fullname}")
    engine = create_async_engine(settings.async_database_url)
    try:
        async with engine.connect() as conn:
            requete = select(doc_schema.c.id, doc_schema.c.name, doc_schema.c.document_type)
            if schema_id is not None:
                requete = requete.where(doc_schema.c.id == schema_id)
            elif not tous:
                requete = requete.where(doc_schema.c.document_type == CERFA_DOCUMENT_TYPE)
            schemas: List[Any] = (await conn.execute(requete.order_by(doc_schema.c.id))).all()
            if not schemas:
                print("aucun schema trouve (essayer --tous)")
                return

            for schema in schemas:
                pages = (
                    await conn.execute(
                        select(schema_page.c.page_number, schema_page.c.description)
                        .where(schema_page.c.schema_id == schema.id)
                        .order_by(schema_page.c.page_number)
                    )
                ).all()
                decrit = func.coalesce(field_spec.c.description, "") != ""
                champs = (
                    await conn.execute(
                        select(
                            field_spec.c.page,
                            func.count().label("total"),
                            func.count().filter(decrit).label("decrits"),
                        )
                        .where(field_spec.c.schema_id == schema.id)
                        .group_by(field_spec.c.page)
                        .order_by(field_spec.c.page)
                    )
                ).all()

                total = sum(c.total for c in champs)
                decrits = sum(c.decrits for c in champs)
                print(f"\n=== schema id={schema.id}  {schema.name}  ({schema.document_type})")
                print(
                    f"    {len(pages)} page(s) decrite(s), {total} champ(s) dont {decrits} decrits"
                )
                par_page = {c.page: c for c in champs}
                numeros = sorted({p.page_number for p in pages} | set(par_page))
                for numero in numeros:
                    description = next(
                        (p.description for p in pages if p.page_number == numero), None
                    )
                    c = par_page.get(numero)
                    compte = f"{c.decrits}/{c.total} champs decrits" if c else "aucun champ"
                    print(f"    page {numero:>2}  [{compte}]")
                    print(f"             {description or '!! PAGE NON DECRITE'}")

                problemes = []
                if not pages:
                    problemes.append(
                        "aucune page decrite : le moteur reconnait les pages "
                        "aux seuls noms de section"
                    )
                if total and decrits < total:
                    problemes.append(
                        f"{total - decrits} champ(s) sans description : display_label servira"
                    )
                if not total:
                    problemes.append("aucun champ : le connecteur refusera d'extraire")
                print("    OK" if not problemes else "    A VOIR : " + " ; ".join(problemes))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("Usage", maxsplit=1)[0])
    parser.add_argument("--schema-id", type=int, help="Schema a verifier")
    parser.add_argument("--tous", action="store_true", help="Tous les schemas de la base")
    args = parser.parse_args()
    asyncio.run(verifier(_paquet_core(), args.schema_id, args.tous))


if __name__ == "__main__":
    main()
