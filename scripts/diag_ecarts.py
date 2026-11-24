"""
scripts/diag_ecarts.py
----------------------
Lecture seule. Explique les ecarts d'une execution de benchmark : combien par
verdict et par nature, et, pour les ecarts de forme (casse, espaces,
ponctuation), les valeurs brutes avec leurs caracteres invisibles.

Usage :
    python scripts/diag_ecarts.py 6
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def _module(nom: str):
    cores = sorted(p.name for p in SRC.glob("*_core") if (p / "models").is_dir())
    return importlib.import_module(f"{cores[0].removesuffix('_core')}_{nom}")


async def diag(execution_id: int) -> None:
    from sqlalchemy import select

    m = _module("core.models")
    R, DF, FS = m.ComparisonResult, m.DocumentField, m.FieldSpec
    async with _module("core.db.session").get_async_session() as db:
        lignes = (
            await db.execute(
                select(R, DF.document_id, FS.section_id, FS.field_key, DF.group_id, FS.value_type)
                .join(DF, DF.id == R.document_field_id)
                .join(FS, FS.id == DF.field_spec_id)
                .where(R.execution_id == execution_id)
            )
        ).all()
    nature = Counter((str(r.verdict), str(r.diff_kind)) for r, *_ in lignes)
    print(f"Execution {execution_id} : {len(lignes)} ecarts\n\nPar verdict et nature :")
    for (v, d), n in nature.most_common():
        print(f"  {v:<10} {d:<12} {n}")
    par_section = Counter((str(r.verdict), s) for r, _, s, *_ in lignes)
    print("\nPar section :")
    for (v, s), n in par_section.most_common(12):
        print(f"  {v:<10} {s:<32} {n}")
    print("\nExemples d'ecarts (repr : montre virgules, retours a la ligne, espaces) :")
    vus = Counter()
    for r, doc, s, cle, groupe, type_ in lignes:
        d = str(r.diff_kind)
        if vus[d] >= 6:
            continue
        vus[d] += 1
        print(f"  [{r.verdict} {d}] doc {doc} {s}.{cle}{f'[{groupe}]' if groupe else ''} ({type_})")
        print(f"      attendu : {r.expected_value!r}")
        print(f"      lu      : {r.observed_value!r}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage : python scripts/diag_ecarts.py <execution_id>")
    os.environ.pop("POSTGRES_DB", None)
    core = _module("core.core.config").get_core_settings()
    _module("core.db.session").init_engine(core.async_database_url, echo=False)
    asyncio.run(diag(int(sys.argv[1])))


if __name__ == "__main__":
    main()