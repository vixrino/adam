"""
scripts/corriger_verite.py
--------------------------
Corrige la verite humaine d'un champ quand l'IHM ne le permet plus (tache
soumise). Met a jour la valeur retenue du champ et la derniere proposition de
chaque job, pour que la verite reste coherente avec l'annotation.

Sans --appliquer, rien n'est ecrit : le script montre l'avant et l'apres.

Usage :
    python scripts/corriger_verite.py 13 cautionnement.nom_adresse_creancier --ligne caution_1
    python scripts/corriger_verite.py 15 certification.signature_deposant --valeur true --appliquer

--valeur absent : le champ devient vide.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def _module(nom: str):
    cores = sorted(p.name for p in SRC.glob("*_core") if (p / "models").is_dir())
    return importlib.import_module(f"{cores[0].removesuffix('_core')}_{nom}")


async def corriger(
    document_id: int, champ: str, ligne: Optional[str], valeur: Optional[str], appliquer: bool
) -> None:
    from sqlalchemy import select

    m = _module("core.models")
    section, _, cle = champ.partition(".")
    async with _module("core.db.session").get_async_session() as db:
        df = (
            await db.execute(
                select(m.DocumentField)
                .join(m.FieldSpec, m.FieldSpec.id == m.DocumentField.field_spec_id)
                .where(
                    m.DocumentField.document_id == document_id,
                    m.FieldSpec.section_id == section,
                    m.FieldSpec.field_key == cle,
                    (
                        m.DocumentField.group_id == ligne
                        if ligne
                        else m.DocumentField.group_id.is_(None)
                    ),
                )
            )
        ).scalar_one_or_none()
        if df is None:
            raise SystemExit(f"document {document_id} : champ {champ} [{ligne}] introuvable")
        propositions = (
            (
                await db.execute(
                    select(m.FieldProposal)
                    .where(m.FieldProposal.document_field_id == df.id)
                    .order_by(m.FieldProposal.created_at, m.FieldProposal.id)
                )
            )
            .scalars()
            .all()
        )
        derniere = {p.job_id: p for p in propositions}
        print(f"document {document_id} {champ}{f'[{ligne}]' if ligne else ''}")
        print(f"  valeur retenue : {df.resolved_value!r} -> {valeur!r}")
        for job_id, p in derniere.items():
            print(f"  proposition du job {job_id} : {p.value!r} -> {valeur!r}")
        if not derniere:
            print("  aucune proposition : le champ n'est pas verifie, la correction ne compte pas")
        df.resolved_value = valeur
        for p in derniere.values():
            p.value = valeur
        if not appliquer:
            await db.rollback()
            print("(sans --appliquer) rien n'est ecrit.")
            return
    print("Corrige.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("document_id", type=int)
    parser.add_argument("champ", help="section.cle, ex. certification.signature_deposant")
    parser.add_argument("--ligne", help="Ligne de tableau, ex. caution_1")
    parser.add_argument("--valeur", help="Nouvelle valeur ; absente = vide")
    parser.add_argument("--appliquer", action="store_true", help="Ecrire (sinon : apercu)")
    args = parser.parse_args()
    os.environ.pop("POSTGRES_DB", None)
    core = _module("core.core.config").get_core_settings()
    _module("core.db.session").init_engine(core.async_database_url, echo=False)
    asyncio.run(corriger(args.document_id, args.champ, args.ligne, args.valeur, args.appliquer))


if __name__ == "__main__":
    main()
