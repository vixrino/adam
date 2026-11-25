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
--csv ecrit en plus les valeurs distinctes de `department` (donnees internes).

Une seule recherche paginee, attribut `department` seul, avec le compte de
service et les exclusions de l'annuaire (AD_EXCLUDE_*). Aucun nom n'est lu.
Le client LDAP n'utilise que les reglages AD_* : il ne depend pas du code de
l'annuaire (dont les noms changent d'une version de nota a l'autre).

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


#: Comptes de personnes actifs : 2 = ACCOUNTDISABLE dans userAccountControl.
PERSONNES_ACTIVES = (
    "(objectCategory=person)(objectClass=user)(!(userAccountControl:1.2.840.113556.1.4.803:=2))"
)


def echapper(valeur: str) -> str:
    """Valeur litterale dans un filtre LDAP (RFC 4515)."""
    remplacements = {"\\": r"\5c", "*": r"\2a", "(": r"\28", ")": r"\29", "\0": r"\00"}
    return "".join(remplacements.get(c, c) for c in valeur)


def _liste(valeur: Any) -> List[str]:
    if isinstance(valeur, str):
        return [v.strip() for v in valeur.split(",") if v.strip()]
    return [str(v).strip() for v in (valeur or []) if str(v).strip()]


class ClientAD:
    """Client LDAP construit sur les seuls reglages AD_* : ne depend pas du code
    de l'annuaire, dont les noms changent d'une version a l'autre."""

    def __init__(self, settings: Any, timeout: int = 60) -> None:
        def reglage(nom: str, defaut: Any = None) -> Any:
            return getattr(settings, nom, defaut)

        manquants = [
            n.upper() for n in ("ad_host", "ad_bind_dn", "ad_password", "ad_base_dn") if not reglage(n)
        ]
        if manquants:
            raise SystemExit(f"reglages AD absents de l'environnement : {', '.join(manquants)}")
        self.host = reglage("ad_host")
        self.port = int(reglage("ad_port", 636))
        self.use_ssl = bool(reglage("ad_use_ssl", True))
        self.bind_dn = reglage("ad_bind_dn")
        self._password = reglage("ad_password")
        self.base_dn = reglage("ad_base_dn")
        self.ca_bundle = reglage("ad_ca_bundle", "") or None
        self.timeout = max(int(reglage("ad_timeout_seconds", 5)), timeout)
        self.prefixes_exclus = _liste(reglage("ad_exclude_prefixes", ""))
        self.suffixes_exclus = _liste(reglage("ad_exclude_suffixes", ""))
        self.ou_exclues = _liste(reglage("ad_exclude_ous", ""))

    def filtre(self, condition: str = "") -> str:
        exclusions = "".join(
            [f"(!(sAMAccountName={echapper(p)}*))" for p in self.prefixes_exclus]
            + [f"(!(sAMAccountName=*{echapper(s)}))" for s in self.suffixes_exclus]
        )
        return f"(&{PERSONNES_ACTIVES}{exclusions}{condition})"

    def exclue(self, dn: Optional[str]) -> bool:
        if not dn or not self.ou_exclues:
            return False
        composants = {c.strip().upper() for c in dn.split(",")}
        return any(f"OU={ou.upper()}" in composants for ou in self.ou_exclues)

    def _connexion(self) -> Any:
        import ssl

        from ldap3 import NONE, SIMPLE, Connection, Server, Tls

        tls = Tls(validate=ssl.CERT_REQUIRED, ca_certs_file=self.ca_bundle) if self.use_ssl else None
        serveur = Server(
            self.host, port=self.port, use_ssl=self.use_ssl, tls=tls, get_info=NONE,
            connect_timeout=self.timeout,
        )
        connexion = Connection(
            serveur, user=self.bind_dn, password=self._password, authentication=SIMPLE,
            receive_timeout=self.timeout, read_only=True,
        )
        if not connexion.bind():
            raise SystemExit(f"liaison au compte de service refusee : {connexion.result}")
        return connexion

    def _entrees(self, connexion: Any, filtre: str) -> Iterable[Dict[str, Any]]:
        from ldap3 import SUBTREE

        for entree in connexion.extend.standard.paged_search(
            self.base_dn, filtre, search_scope=SUBTREE, attributes=["department"],
            paged_size=500, generator=True,
        ):
            if entree.get("type") == "searchResEntry" and not self.exclue(entree.get("dn")):
                yield entree

    @staticmethod
    def _departement(entree: Dict[str, Any]) -> str:
        valeur = entree.get("attributes", {}).get("department")
        if isinstance(valeur, list):
            valeur = valeur[0] if valeur else None
        return " ".join(str(valeur).split()) if valeur else ""

    def departements(self) -> Counter:
        connexion = self._connexion()
        try:
            return Counter(self._departement(e) for e in self._entrees(connexion, self.filtre()))
        finally:
            connexion.unbind()

    async def trouver(self, matricule: str) -> Optional[Any]:
        """La personne au matricule donne (department seul), ou None."""
        import asyncio
        from types import SimpleNamespace

        def chercher() -> Optional[Any]:
            connexion = self._connexion()
            try:
                filtre = self.filtre(f"(sAMAccountName={echapper(matricule.strip())})")
                trouvees = list(self._entrees(connexion, filtre))
            finally:
                connexion.unbind()
            if len(trouvees) != 1:
                return None
            return SimpleNamespace(departement=self._departement(trouvees[0]) or None)

        return await asyncio.to_thread(chercher)


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--min-comptes", type=int, default=5, help="Masquer les mots plus rares")
    parser.add_argument(
        "--csv",
        help="Ecrire aussi les valeurs distinctes dans ce fichier (donnees internes : ne pas commiter)",
    )
    args = parser.parse_args()

    from seed_organisations import ORGANISATIONS

    settings = _module("api.core.config").settings
    departements = ClientAD(settings).departements()
    slugs = [slug for slug, _ in ORGANISATIONS]
    defaut = getattr(settings, "ad_organisation_defaut", "") or ""
    print("\n".join(rapport(departements, slugs, defaut, args.min_comptes)))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            ecrit = csv.writer(f, delimiter=";")
            ecrit.writerow(["department", "comptes", "organisation a la connexion"])
            for valeur, n in departements.most_common():
                ecrit.writerow([valeur, n, organisation_de(valeur, slugs) or "(defaut)"])
        print(f"\nvaleurs distinctes ecrites dans {args.csv}")


if __name__ == "__main__":
    main()
