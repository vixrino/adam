"""
scripts/ddl_metriques.py
------------------------
Cree les colonnes des metriques du benchmark sur une base non suivie par
alembic, sans passer par l'etat que calcule migrer_expected_page_count.py.

Avant sa correction, ce script-la jugeait la base a jour des que
test_recipe.config existait, et ne creait donc pas
test_execution.comparateur_version : le worker de benchmark plantait a chaque
cycle. Ici, le DDL direct est joue sans condition ; chaque instruction est en
IF NOT EXISTS, le relancer ne change rien.

Le paquet *_core est trouve sous src/ : le script tourne tel quel dans les deux
depots, depuis la racine du depot (.env).

Usage :
    python scripts/ddl_metriques.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import migrer_expected_page_count as migrer  # noqa: E402


def main() -> None:
    """Joue le DDL direct sur la base du .env et dit quel paquet a servi."""
    core, _ = migrer._paquet_core()
    asyncio.run(migrer._ddl_direct(core))
    print(f" {core} : colonnes des metriques en place ({len(migrer.DDL_DIRECT)} instructions)")


if __name__ == "__main__":
    main()
