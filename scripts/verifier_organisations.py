"""
scripts/verifier_organisations.py
---------------------------------
Lecture seule. Verifie les organisations sans attendre qu'un agent se connecte.

1. Chaque slug d'ORGANISATIONS (seed_organisations.py) existe en base ; les
   organisations en base hors de la liste sont signalees.
2. AD_ORGANISATION_DEFAUT designe une organisation qui existe.
3. Pour chaque utilisateur en base : son `department` AD, l'organisation que
   la regle de connexion lui donne (mot le plus a gauche egal a un slug, sinon
   le defaut) et celle qu'il a. Un ecart est normal pour un compte cree avant
   l'organisation attendue (l'organisation se fixe a la premiere connexion) ;
   il est signale comme ANORMAL sinon.
4. --matricule : meme calcul pour quelqu'un qui n'est pas encore dans nota.

Une recherche AD par utilisateur, par le compte de service.

Usage :
    uv run python scripts/verifier_organisations.py
    uv run python scripts/verifier_organisations.py --matricule I659418 --matricule V654846
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lister_directions import _annuaire, _module, organisation_de  # noqa: E402
from seed_organisations import ORGANISATIONS  # noqa: E402


def attendue(departement: Optional[str], slugs: List[str], defaut: str) -> str:
    return organisation_de(departement or "", slugs) or defaut or "(aucune -> 403)"


def verdict(
    actuelle: str, prevue: str, cree_le: Optional[datetime], org_prevue_le: Optional[datetime]
) -> str:
    if actuelle == prevue:
        return "ok"
    if cree_le and org_prevue_le and cree_le < org_prevue_le:
        return "ancien compte"
    return "ANORMAL"


async def verifier(matricules: List[str]) -> int:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    models = _module("core.models")
    Organisation, User = models.Organisation, models.User
    session_mod = _module("core.db.session")
    settings = _module("api.core.config").settings
    defaut = (getattr(settings, "ad_organisation_defaut", "") or "").strip().lower()
    annuaire = _annuaire(_module("api.services.annuaire"), settings)

    session_mod.init_engine(_module("core.core.config").CoreSettings().async_database_url)
    factory = async_sessionmaker(bind=session_mod.get_engine(), expire_on_commit=False)
    problemes = 0
    try:
        async with factory() as session:
            orgs = (await session.execute(select(Organisation))).scalars().all()
            par_slug: Dict[str, Any] = {o.slug: o for o in orgs if o.deleted_at is None}
            par_id = {o.id: o.slug for o in orgs}

            print("== 1. organisations")
            for slug, _ in ORGANISATIONS:
                ok = slug in par_slug
                problemes += not ok
                print(f"  {slug:<12} {'ok' if ok else 'MANQUANTE : lancer seed_organisations.py'}")
            hors = sorted(set(par_slug) - {s for s, _ in ORGANISATIONS})
            if hors:
                print(f"  en base hors de la liste : {', '.join(hors)}")

            print("\n== 2. AD_ORGANISATION_DEFAUT")
            if defaut in par_slug:
                print(f"  {defaut} : ok")
            else:
                problemes += 1
                print(f"  {defaut or '(vide)'} : AUCUNE organisation de ce slug -> 403 hors liste")

            slugs = list(par_slug)
            users = (
                (await session.execute(select(User).where(User.deleted_at.is_(None))))
                .scalars()
                .all()
            )
            print(f"\n== 3. utilisateurs en base ({len(users)})")
            print(f"  {'matricule':<10} {'a':<10} {'attendue':<10} {'verdict':<14} department")
            for u in users:
                personne = await annuaire.trouver(u.matricule)
                dep = personne.departement if personne else None
                prevue = attendue(dep, slugs, defaut)
                actuelle = par_id.get(u.organisation_id, "?")
                org = par_slug.get(prevue)
                v = verdict(actuelle, prevue, u.created_at, org.created_at if org else None)
                problemes += v == "ANORMAL"
                absent = "" if personne else "(absent de l'AD)"
                print(f"  {u.matricule:<10} {actuelle:<10} {prevue:<10} {v:<14} {dep or absent}")

            if matricules:
                print("\n== 4. personnes pas encore connectees")
                for m in matricules:
                    personne = await annuaire.trouver(m)
                    if personne is None:
                        print(f"  {m:<10} absent de l'AD (ou compte exclu)")
                        continue
                    prevue = attendue(personne.departement, slugs, defaut)
                    print(f"  {m:<10} -> {prevue:<10} {personne.departement or '(sans department)'}")
    finally:
        await session_mod.get_engine().dispose()

    print(f"\n{problemes} probleme(s)." if problemes else "\nAucun probleme.")
    return 1 if problemes else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--matricule", action="append", default=[], help="Personne a tester")
    args = parser.parse_args()
    sys.exit(asyncio.run(verifier(args.matricule)))


if __name__ == "__main__":
    main()
