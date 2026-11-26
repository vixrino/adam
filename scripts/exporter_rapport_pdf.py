"""
scripts/exporter_rapport_pdf.py
-------------------------------
Ecrit le PDF du rapport de qualite d'extraction d'une execution de benchmark,
sans IHM ni jeton : le script appelle le meme code que la route
GET /test-executions/{id}/metriques.pdf, directement sur la base du .env.

Lecture seule : aucune ecriture en base.

Le paquet *_core est trouve sous src/ : le script tourne tel quel dans adam et
dans nota, depuis la racine du depot.

Usage :
    python scripts/exporter_rapport_pdf.py                  # liste les executions finies
    python scripts/exporter_rapport_pdf.py 12               # rapport_test_12.pdf
    python scripts/exporter_rapport_pdf.py 12 --sortie r.pdf --reussite-inferieure-a 0.7
    python scripts/exporter_rapport_pdf.py 12 --type-champ NUMBER --type-erreur fausse
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import sys
from pathlib import Path
from typing import Any, List, Optional

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


def _prefixe() -> str:
    """'adam' ou 'nota', d'apres le paquet *_core present sous src/."""
    cores = sorted(p.name for p in SRC.glob("*_core") if (p / "models").is_dir())
    if len(cores) != 1:
        raise SystemExit(f"attendu un *_core sous src/, trouve {cores}")
    return cores[0].removesuffix("_core")


def _module(nom: str) -> Any:
    return importlib.import_module(f"{_prefixe()}_{nom}")


async def _lister() -> None:
    from sqlalchemy import select

    modeles = _module("core.models")
    session_mod = _module("core.db.session")
    async with session_mod.get_async_session() as db:
        lignes = (
            await db.execute(
                select(
                    modeles.TestExecution.id,
                    modeles.TestExecution.recipe_id,
                    modeles.TestExecution.status,
                    modeles.TestExecution.documents_compared,
                    modeles.TestExecution.finished_at,
                ).order_by(modeles.TestExecution.id.desc())
            )
        ).all()
    if not lignes:
        print("Aucune execution en base.")
        return
    print(f"{'id':>5}  {'recette':>7}  {'statut':<10}  {'documents':>9}  fin")
    for id_, recette, statut, documents, fin in lignes:
        print(f"{id_:>5}  {recette:>7}  {statut:<10}  {documents or 0:>9}  {fin or '-'}")
    print("\nPuis : python scripts/exporter_rapport_pdf.py <id>")


async def _exporter(execution_id: int, filtres: Any, sortie: Path) -> None:
    from fastapi import HTTPException

    router = _module("api.routers.benchmark")
    session_mod = _module("core.db.session")
    async with session_mod.get_async_session() as db:
        try:
            reponse = await router.metriques_pdf(execution_id, filtres, None, db)
        except HTTPException as erreur:
            raise SystemExit(f"execution {execution_id} : {erreur.detail}") from erreur
    sortie.write_bytes(reponse.body)
    print(f"PDF ecrit : {sortie.resolve()} ({len(reponse.body) // 1024} Ko)")


def main(arguments: Optional[List[str]] = None) -> None:
    """Point d'entree en ligne de commande."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("execution_id", nargs="?", type=int, help="Sans id : liste les executions")
    parser.add_argument("--sortie", type=Path, help="Fichier PDF (defaut rapport_test_<id>.pdf)")
    parser.add_argument("--recherche")
    parser.add_argument("--type-champ", action="append", default=[], help="TEXT, NUMBER...")
    parser.add_argument("--reussite-inferieure-a", type=float)
    parser.add_argument(
        "--type-erreur", action="append", default=[], choices=["fausse", "manquee", "inventee"]
    )
    parser.add_argument("--section", action="append", default=[])
    args = parser.parse_args(arguments)

    core = _module("core.core.config").get_core_settings()
    _module("core.db.session").init_engine(core.async_database_url)

    if args.execution_id is None:
        asyncio.run(_lister())
        return
    filtres = _module("core.benchmark.metriques").FiltresChamps(
        recherche=args.recherche,
        types_champ=tuple(args.type_champ),
        reussite_inferieure_a=args.reussite_inferieure_a,
        types_erreur=tuple(args.type_erreur),
        sections=tuple(args.section),
    )
    sortie = args.sortie or Path(f"rapport_test_{args.execution_id}.pdf")
    asyncio.run(_exporter(args.execution_id, filtres, sortie))


if __name__ == "__main__":
    main()
