"""
scripts/nettoyer_tables_residuelles.py
--------------------------------------
Repere, et sur demande supprime, les tables residuelles de public qui portent
le nom d'une table de l'application.

Dans nota, les tables vivent dans le schema PostgreSQL « nota ». Une base
creee avec l'ancienne chaine de migrations garde, a cote, des copies perimees
dans public (public.doc_schema, public.field_spec...). Elles ne servent plus,
mais une requete SQL ecrite sans prefixe de schema les lit a la place des
vraies : c'est ce qui a fait afficher a verifier_schema.py un seul schema
(CERFA id=11) au lieu de ceux de l'application (26/11).

Prudence, la base pouvant etre partagee :
- seules les tables de public dont le nom est celui d'une table des modeles
  sont visees ; tout le reste de public (autres applications, alembic_version,
  que lit rattraper_baseline.py) est ignore ;
- sans --appliquer, le script liste et ne touche a rien ;
- avec --appliquer, tout part dans une seule transaction, sans CASCADE : si
  une table qui n'est pas visee depend de l'une d'elles, la base refuse, et
  rien n'est supprime ;
- sans schema propre a l'application (adam : tout est dans public), il n'y a
  rien de residuel et le script s'arrete.

Faire une sauvegarde avant --appliquer (pg_dump), la suppression est
definitive.

Le paquet *_core est trouve sous src/ : le script tourne tel quel dans les deux
depots, depuis la racine du depot (.env).

Usage :
    uv run python scripts/nettoyer_tables_residuelles.py              # liste seulement
    uv run python scripts/nettoyer_tables_residuelles.py --appliquer
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Sequence

from sqlalchemy import MetaData, Table, func, inspect, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

SCHEMA_RESIDUEL = "public"


@dataclass(frozen=True)
class TableResiduelle:
    nom: str
    lignes_residuelles: int
    #: Lignes de la vraie table, dans le schema de l'application ; None si elle n'y est pas.
    lignes_application: Optional[int]


def _paquet_core() -> str:
    trouves = sorted(p.name for p in SRC.glob("*_core") if (p / "core" / "config.py").is_file())
    if len(trouves) != 1:
        raise SystemExit(f"attendu un seul src/*_core, trouve : {trouves}")
    return trouves[0]


def noms_residuels(dans_public: Sequence[str], de_l_application: Sequence[str]) -> List[str]:
    """Tables de public qui portent le nom d'une table de l'application."""
    return sorted(set(dans_public) & set(de_l_application))


def _compter(connexion: Any, nom: str, schema: str) -> int:
    table = Table(nom, MetaData(), schema=schema)
    return int(connexion.execute(select(func.count()).select_from(table)).scalar_one())


def recenser(
    connexion: Any, schema_application: str, tables_application: Sequence[str]
) -> List[TableResiduelle]:
    """Les tables residuelles et leur nombre de lignes, de part et d'autre."""
    inspecteur = inspect(connexion)
    dans_public = inspecteur.get_table_names(schema=SCHEMA_RESIDUEL)
    dans_application = set(inspecteur.get_table_names(schema=schema_application))
    return [
        TableResiduelle(
            nom=nom,
            lignes_residuelles=_compter(connexion, nom, SCHEMA_RESIDUEL),
            lignes_application=(
                _compter(connexion, nom, schema_application) if nom in dans_application else None
            ),
        )
        for nom in noms_residuels(dans_public, tables_application)
    ]


def supprimer(connexion: Any, noms: Sequence[str]) -> None:
    """Supprime ces tables de public, dans l'ordre de leurs dependances, sans CASCADE."""
    residuelles = MetaData(schema=SCHEMA_RESIDUEL)
    residuelles.reflect(bind=connexion, schema=SCHEMA_RESIDUEL, only=list(noms))
    residuelles.drop_all(bind=connexion)


def afficher(tables: Sequence[TableResiduelle], schema_application: str) -> None:
    print(f"{'table':28} {'lignes ' + SCHEMA_RESIDUEL:>14} {'lignes ' + schema_application:>14}")
    for t in tables:
        app = "absente" if t.lignes_application is None else str(t.lignes_application)
        print(f"{t.nom:28} {t.lignes_residuelles:>14} {app:>14}")


async def principal(appliquer: bool) -> int:
    core = _paquet_core()
    settings = importlib.import_module(f"{core}.core.config").get_core_settings()
    base = importlib.import_module(f"{core}.db.base").Base
    schema_application = base.metadata.schema
    if not schema_application or schema_application == SCHEMA_RESIDUEL:
        print(f"Les tables de l'application sont dans {SCHEMA_RESIDUEL} : rien de residuel.")
        return 0
    tables_application = [t.name for t in base.metadata.sorted_tables]

    engine = create_async_engine(settings.async_database_url)
    try:
        async with engine.connect() as conn:
            tables = await conn.run_sync(recenser, schema_application, tables_application)
        if not tables:
            print(f"Aucune table residuelle dans {SCHEMA_RESIDUEL}.")
            return 0
        afficher(tables, schema_application)
        if not appliquer:
            print(f"\n{len(tables)} table(s) residuelle(s). Rien n'est supprime sans --appliquer.")
            return 0
        try:
            async with engine.begin() as conn:
                await conn.run_sync(supprimer, [t.nom for t in tables])
        except DBAPIError as exc:
            cause = getattr(exc, "orig", exc)
            print(f"\nRefuse par la base, rien n'est supprime : {type(cause).__name__} : {cause}")
            return 1
        print(f"\n{len(tables)} table(s) supprimee(s) de {SCHEMA_RESIDUEL}.")
        return 0
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("Usage", maxsplit=1)[0])
    parser.add_argument(
        "--appliquer", action="store_true", help="supprimer les tables listees (definitif)"
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(principal(args.appliquer)))


if __name__ == "__main__":
    main()
