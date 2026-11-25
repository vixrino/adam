"""
scripts/seed_organisations.py
-----------------------------
Cree les organisations de la Banque de France qui manquent. Rejouable.

A la premiere connexion, l'organisation d'un agent se deduit de son attribut
AD `department` : chaque mot, en minuscules, est compare aux slugs de la table
organisation, le plus a gauche gagne. Sans organisation correspondante ni
AD_ORGANISATION_DEFAUT valide, l'agent est refuse (403). Les organisations
doivent donc exister avant l'ouverture aux agents.

Independant de seed.py, qui vide les tables : ne jamais lancer seed.py sur la
base deployee. Ce script-ci cree, par slug, ce qui manque ; il ne modifie ni ne
supprime rien (une organisation existante garde son nom, une organisation
supprimee logiquement n'est pas recreee) et ne cree ni utilisateur ni projet.

A lancer apres `launcher.py migrate`, a chaque deploiement.

Usage :
    python scripts/seed_organisations.py --apercu   # ce qui serait cree, sans ecrire
    python scripts/seed_organisations.py
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import re
import sys
from pathlib import Path
from typing import Any, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

#: (slug = mot de l'attribut AD `department` en minuscules, nom affiche).
#: Les directions sont le 2e mot de `department` (RE1 US2183 DGSI DIRES SOLAPS) :
#: liste tiree de l'AD par lister_directions.py le 25/11/2026, comptes actifs.
ORGANISATIONS: List[Tuple[str, str]] = [
    ("dgsi", "DGSI"),  # 3622 comptes
    ("dgsei", "DGSEI"),  # 1084
    ("dgso", "DGSO"),  # 911
    ("sgacpr", "SGACPR"),  # 575
    ("dgrh", "DGRH"),  # 431
    ("sg", "SG"),  # 393
    ("dgser", "DGSER"),  # 374
    ("dgmp", "DGMP"),  # 295
    ("cg", "CG"),  # 180
    ("cabgouv", "CABGOUV"),  # 6
]

SLUG = re.compile(r"^[a-z0-9-]+$")


def _module(nom: str) -> Any:
    """adam_<nom> ou nota_<nom> : le script se copie tel quel d'un depot a l'autre."""
    cores = sorted(p.name for p in SRC.glob("*_core") if (p / "models").is_dir())
    if len(cores) != 1:
        raise SystemExit(f"attendu un *_core sous src/, trouve {cores}")
    return importlib.import_module(f"{cores[0].removesuffix('_core')}_{nom}")


def verifier(organisations: Iterable[Tuple[str, str]]) -> None:
    """Refuse un slug mal forme ou en double avant de toucher a la base."""
    vus = set()
    for slug, nom in organisations:
        if not SLUG.match(slug):
            raise SystemExit(f"slug invalide {slug!r} : minuscules, chiffres et tirets")
        if slug in vus:
            raise SystemExit(f"slug en double : {slug!r}")
        if not nom.strip():
            raise SystemExit(f"nom vide pour {slug!r}")
        vus.add(slug)


def a_creer(
    organisations: Iterable[Tuple[str, str]], existants: Iterable[str]
) -> List[Tuple[str, str]]:
    deja = set(existants)
    return [(slug, nom) for slug, nom in organisations if slug not in deja]


async def seed(apercu: bool) -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    verifier(ORGANISATIONS)
    Organisation = _module("core.models").Organisation
    session_mod = _module("core.db.session")
    settings = _module("core.core.config").CoreSettings()

    session_mod.init_engine(settings.async_database_url, echo=False)
    factory = async_sessionmaker(bind=session_mod.get_engine(), expire_on_commit=False)
    try:
        async with factory() as session:
            # Supprimees logiquement comprises : le slug est unique en base.
            existants = (await session.execute(select(Organisation.slug))).scalars().all()
            nouvelles = a_creer(ORGANISATIONS, existants)
            for slug, nom in ORGANISATIONS:
                etat = "a creer" if (slug, nom) in nouvelles else "existe deja"
                print(f"  {slug:<12} {nom:<30} {etat}")
            if apercu:
                print(f"\n(--apercu) {len(nouvelles)} organisation(s) a creer, rien n'est ecrit.")
                return
            session.add_all(Organisation(slug=slug, name=nom) for slug, nom in nouvelles)
            await session.commit()
            print(f"\n{len(nouvelles)} organisation(s) creee(s).")
    finally:
        await session_mod.get_engine().dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apercu", action="store_true", help="Lister sans ecrire")
    args = parser.parse_args()
    asyncio.run(seed(args.apercu))


if __name__ == "__main__":
    main()
