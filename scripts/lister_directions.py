"""
scripts/lister_directions.py
----------------------------
Lecture seule. Lit l'attribut AD `department` de tous les comptes actifs pour
dresser la liste des directions a mettre dans seed_organisations.ORGANISATIONS.

A la connexion, chaque mot de `department`, en minuscules, est compare aux slugs
des organisations ; le plus a gauche gagne. Le script affiche donc :
1. les mots trouves dans `department`, avec le nombre de comptes qui les portent
   et leur position habituelle (1er mot, 2e mot...) ;
2. ce que donnerait la liste actuelle d'ORGANISATIONS : combien de comptes
   chaque organisation recevrait, et combien tomberaient sur
   AD_ORGANISATION_DEFAUT.
Les valeurs distinctes de `department` sont ecrites dans departements.csv.

Une seule recherche paginee, attribut `department` seul, avec le compte de
service et les exclusions de l'annuaire (AD_EXCLUDE_*). Aucun nom n'est lu.

Usage :
    uv run python scripts/lister_directions.py
    uv run python scripts/lister_directions.py --min-comptes 20
"""

from __future__ import annotations

import argparse
import csv
import importlib
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _module(nom: str) -> Any:
    """adam_<nom> ou nota_<nom> : le script se copie tel quel d'un depot a l'autre."""
    cores = sorted(p.name for p in SRC.glob("*_core") if (p / "models").is_dir())
    if len(cores) != 1:
        raise SystemExit(f"attendu un *_core sous src/, trouve {cores}")
    return importlib.import_module(f"{cores[0].removesuffix('_core')}_{nom}")


def organisation_de(departement: str, slugs: Iterable[str]) -> Optional[str]:
    """Meme regle que la connexion : le mot le plus a gauche qui est un slug."""
    connus = set(slugs)
    for mot in departement.split():
        if mot.lower() in connus:
            return mot.lower()
    return None


def lire_departements(annuaire: Any, ldap: Any) -> Counter:
    from ldap3 import SUBTREE

    filtre = f"(&{ldap._PERSONNES_ACTIVES}" + ldap._exclusions(
        annuaire.prefixes_exclus, annuaire.suffixes_exclus
    ) + ")"
    connexion = annuaire._connexion()
    if not connexion.bind():
        raise SystemExit(f"liaison au compte de service refusee : {connexion.result}")
    comptes: Counter = Counter()
    try:
        for entree in connexion.extend.standard.paged_search(
            annuaire.base_dn,
            filtre,
            search_scope=SUBTREE,
            attributes=["department"],
            paged_size=500,
            generator=True,
        ):
            if entree.get("type") != "searchResEntry":
                continue
            if ldap.dans_ou_exclue(entree.get("dn"), annuaire.ou_exclues):
                continue
            valeur = entree.get("attributes", {}).get("department")
            if isinstance(valeur, list):
                valeur = valeur[0] if valeur else None
            comptes[" ".join(str(valeur).split()) if valeur else ""] += 1
    finally:
        connexion.unbind()
    return comptes


def rapport(departements: Counter, slugs: Sequence[str], defaut: str, min_comptes: int) -> List[str]:
    par_mot: Counter = Counter()
    positions: Dict[str, Counter] = defaultdict(Counter)
    for valeur, n in departements.items():
        for i, mot in enumerate(dict.fromkeys(valeur.split()), start=1):
            par_mot[mot] += n
            positions[mot][i] += n

    total = sum(departements.values())
    lignes = [
        f"{total} comptes actifs, {len(departements)} valeurs distinctes de department "
        f"({departements.get('', 0)} comptes sans department)",
        "",
        f"== mots de department portes par au moins {min_comptes} comptes",
        f"  {'mot':<14} {'comptes':>8}  position habituelle",
    ]
    for mot, n in par_mot.most_common():
        if n < min_comptes:
            break
        pos, _ = positions[mot].most_common(1)[0]
        marque = "  <- deja dans ORGANISATIONS" if mot.lower() in slugs else ""
        lignes.append(f"  {mot:<14} {n:>8}  {pos}{'er' if pos == 1 else 'e'} mot{marque}")

    repartition: Counter = Counter()
    for valeur, n in departements.items():
        repartition[organisation_de(valeur, slugs) or f"(defaut : {defaut or 'aucun -> 403'})"] += n
    lignes += ["", "== avec la liste actuelle d'ORGANISATIONS, a la connexion"]
    for org, n in repartition.most_common():
        lignes.append(f"  {org:<30} {n:>8} comptes")
    return lignes


#: Parametre du client -> reglage AD de l'environnement (adam et nota).
_REGLAGES = {
    "host": "ad_host",
    "port": "ad_port",
    "use_ssl": "ad_use_ssl",
    "bind_dn": "ad_bind_dn",
    "password": "ad_password",
    "base_dn": "ad_base_dn",
    "ca_bundle": "ad_ca_bundle",
    "timeout_seconds": "ad_timeout_seconds",
    "limite": "ad_search_limit",
    "prefixes_exclus": "ad_exclude_prefixes",
    "suffixes_exclus": "ad_exclude_suffixes",
    "ou_exclues": "ad_exclude_ous",
}


def _appeler(fabrique: Any, settings: Any) -> Any:
    """Appelle une fabrique (fonction ou classe) avec ce qu'elle demande :
    les settings, enabled=True (l'interrupteur de l'IHM : ce script lit l'AD
    quel que soit l'interrupteur), ou les reglages AD un par un."""
    import inspect

    args: Dict[str, Any] = {}
    for nom, param in inspect.signature(fabrique).parameters.items():
        if nom in ("settings", "config", "reglages"):
            args[nom] = settings
        elif nom == "enabled":
            args[nom] = True
        elif nom in _REGLAGES or hasattr(settings, f"ad_{nom}"):
            valeur = getattr(settings, _REGLAGES.get(nom, f"ad_{nom}"))
            if nom.endswith(("exclus", "exclues")) and isinstance(valeur, str):
                valeur = [v.strip() for v in valeur.split(",") if v.strip()]
            args[nom] = valeur
        elif param.default is inspect.Parameter.empty and param.kind not in (
            param.VAR_POSITIONAL,
            param.VAR_KEYWORD,
        ):
            raise TypeError(f"parametre {nom!r} inconnu")
    return fabrique(**args)


def _annuaire(ldap: Any, settings: Any) -> Any:
    """Le client AD du code en place, quel que soit le nom de sa fabrique.

    adam : annuaire_depuis_settings(settings) ; nota y a ajoute `enabled`, puis
    l'a remplacee. On essaie les fonctions du module qui parlent d'annuaire,
    puis la classe qui sait `trouver` et ouvrir une `_connexion`."""
    import inspect

    candidats = [
        f
        for nom, f in inspect.getmembers(ldap, inspect.isfunction)
        if f.__module__ == ldap.__name__
        and "annuaire" in nom.lower()
        and not nom.startswith("_")
        and any(p in inspect.signature(f).parameters for p in ("settings", "config", "reglages"))
    ] + [
        c
        for _, c in inspect.getmembers(ldap, inspect.isclass)
        if c.__module__ == ldap.__name__ and hasattr(c, "trouver") and hasattr(c, "_connexion")
    ]
    erreurs = []
    for fabrique in candidats:
        try:
            client = _appeler(fabrique, settings)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            erreurs.append(f"  {fabrique.__name__}{inspect.signature(fabrique)} : {exc}")
            continue
        if hasattr(client, "trouver") and hasattr(client, "_connexion"):
            return client
        erreurs.append(f"  {fabrique.__name__} : renvoie {type(client).__name__}, pas un client AD")

    contenu = [
        f"  {nom}{inspect.signature(obj) if callable(obj) else ''}"
        for nom, obj in inspect.getmembers(ldap)
        if not nom.startswith("__")
        and (inspect.isfunction(obj) or inspect.isclass(obj))
        and getattr(obj, "__module__", "") == ldap.__name__
    ]
    raise SystemExit(
        f"aucun moyen d'ouvrir l'annuaire dans {ldap.__name__}.\n"
        + ("essais :\n" + "\n".join(erreurs) + "\n" if erreurs else "")
        + "contenu du module (a me coller) :\n"
        + "\n".join(contenu)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--min-comptes", type=int, default=5, help="Masquer les mots plus rares")
    parser.add_argument("--csv", default="departements.csv", help="Fichier des valeurs distinctes")
    args = parser.parse_args()

    from seed_organisations import ORGANISATIONS

    ldap = _module("api.services.annuaire")
    settings = _module("api.core.config").settings
    annuaire = _annuaire(ldap, settings)
    annuaire.timeout_seconds = max(annuaire.timeout_seconds, 60)

    departements = lire_departements(annuaire, ldap)
    slugs = [slug for slug, _ in ORGANISATIONS]
    defaut = getattr(settings, "ad_organisation_defaut", "") or ""
    print("\n".join(rapport(departements, slugs, defaut, args.min_comptes)))

    with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
        ecrit = csv.writer(f, delimiter=";")
        ecrit.writerow(["department", "comptes", "organisation a la connexion"])
        for valeur, n in departements.most_common():
            ecrit.writerow([valeur, n, organisation_de(valeur, slugs) or "(defaut)"])
    print(f"\nvaleurs distinctes ecrites dans {args.csv}")


if __name__ == "__main__":
    main()
