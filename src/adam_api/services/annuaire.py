"""Recherche de personnes dans l'Active Directory, par le compte de service.

Sert a affecter quelqu'un a un projet avant sa premiere connexion : on le
cherche dans l'annuaire, on retient son matricule (sAMAccountName), et la ligne
`user` est creee a partir de sa fiche AD. A sa premiere connexion, le matricule
porte par son token tombe sur cette ligne.

Regles de recherche, fixees avec l'equipe qui administre l'AD
--------------------------------------------------------------
- Sans filtre, une recherche ramene plus de 10 000 comptes et prend plusieurs
  secondes : il faut au moins `ad_min_chars` caracteres (3 par defaut).
- Une requete au plus toutes les `ad_rate_seconds` secondes par utilisateur
  (2 par defaut), pour affiner au fil de la saisie sans saturer l'AD.
- Les comptes desactives sont exclus (bit ACCOUNTDISABLE de userAccountControl).
- L'attribut `department` est rendu : il situe la personne dans le reseau et
  permet de grouper la liste deroulante.
- Certains comptes rangés sous la base de recherche ne sont pas des personnes a
  affecter (comptes d'administration, dont le matricule finit par « OT2 », par
  exemple). Ils s'excluent par le debut ou la fin de leur matricule
  (AD_EXCLUDE_PREFIXES, AD_EXCLUDE_SUFFIXES, appliques dans le filtre LDAP) ou
  par l'unite d'organisation qui les range (AD_EXCLUDE_OUS, appliquee sur le DN
  de chaque resultat, que LDAP ne sait pas filtrer).

Connexion
---------
LDAPS, port 636, liaison simple avec le DN du compte de service. Le mot de
passe ne vit que dans l'environnement (AD_PASSWORD), jamais dans le code ni
dans un commit. Le certificat du serveur est verifie, contre AD_CA_BUNDLE s'il
est fourni.

La bibliotheque ldap3 est synchrone : chaque appel part dans un thread, avec une
connexion ouverte et fermee a chaque recherche — quelques recherches par minute
ne justifient pas un pool.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence

from adam_core.utils.logging import get_logger

logger = get_logger(__name__)

#: Attributs lus sur chaque compte.
ATTRIBUTS = ["sAMAccountName", "displayName", "mail", "givenName", "sn", "department"]

#: Comptes de personnes, desactives exclus. La regle de correspondance
#: 1.2.840.113556.1.4.803 est le ET bit a bit de l'AD : 2 = ACCOUNTDISABLE.
_PERSONNES_ACTIVES = (
    "(objectCategory=person)(objectClass=user)" "(!(userAccountControl:1.2.840.113556.1.4.803:=2))"
)

#: Au-dela, la saisie est trop vague pour etre utile : les premiers mots suffisent.
_MOTS_MAX = 3


class AnnuaireErreur(Exception):
    """L'annuaire n'a pas pu repondre (injoignable, liaison refusee...)."""


class AnnuaireDesactive(AnnuaireErreur):
    """AD_ENABLED est faux, ou la configuration est incomplete."""


@dataclass(frozen=True)
class PersonneAnnuaire:
    """Une personne de l'AD, telle que l'IHM la propose et que `user` la stocke."""

    matricule: str
    nom_affiche: str
    email: Optional[str]
    prenom: Optional[str]
    nom: Optional[str]
    departement: Optional[str]


class Annuaire(Protocol):
    async def rechercher(self, texte: str) -> List[PersonneAnnuaire]: ...

    async def trouver(self, matricule: str) -> Optional[PersonneAnnuaire]: ...


# -- Filtres LDAP (fonctions pures, testables sans AD) --------------------------


def echapper(valeur: str) -> str:
    """Echappe une valeur saisie pour un filtre LDAP (RFC 4515).

    Sans cela, une saisie contenant `*`, `(` ou `)` changerait le filtre lui-meme
    au lieu d'etre cherchee : c'est l'equivalent LDAP d'une injection SQL.
    """
    remplacements = {"\\": r"\5c", "*": r"\2a", "(": r"\28", ")": r"\29", "\0": r"\00"}
    return "".join(remplacements.get(c, c) for c in valeur)


def _exclusions(prefixes: Sequence[str], suffixes: Sequence[str] = ()) -> str:
    """Conditions qui ecartent les matricules commencant par l'un des prefixes
    ou finissant par l'un des suffixes."""
    return "".join(
        [f"(!(sAMAccountName={echapper(p.strip())}*))" for p in prefixes if p.strip()]
        + [f"(!(sAMAccountName=*{echapper(s.strip())}))" for s in suffixes if s.strip()]
    )


def filtre_recherche(
    texte: str, prefixes_exclus: Sequence[str] = (), suffixes_exclus: Sequence[str] = ()
) -> str:
    """Filtre pour une saisie libre : chaque mot doit correspondre a un debut de
    matricule, de prenom ou de nom, ou a un morceau du nom affiche."""
    mots = [echapper(m) for m in texte.split()[:_MOTS_MAX]]
    conditions = "".join(
        f"(|(sAMAccountName={m}*)(givenName={m}*)(sn={m}*)(displayName=*{m}*))" for m in mots
    )
    exclusions = _exclusions(prefixes_exclus, suffixes_exclus)
    return f"(&{_PERSONNES_ACTIVES}{exclusions}{conditions})"


def filtre_matricule(
    matricule: str, prefixes_exclus: Sequence[str] = (), suffixes_exclus: Sequence[str] = ()
) -> str:
    """Filtre exact sur un matricule, comptes actifs seulement. Les exclusions
    valent ici aussi : un compte ecarte de la recherche ne doit pas pouvoir
    etre affecte en tapant son matricule."""
    return (
        f"(&{_PERSONNES_ACTIVES}{_exclusions(prefixes_exclus, suffixes_exclus)}"
        f"(sAMAccountName={echapper(matricule.strip())}))"
    )


def dans_ou_exclue(dn: Optional[str], ou_exclues: Sequence[str]) -> bool:
    """Le DN passe-t-il par l'une des unites d'organisation exclues ?

    Compare les composants « OU=... » du DN, sans casse : OU=OT2 exclut
    CN=x,OU=OT2,OU=T2,DC=... mais pas CN=x,OU=OT2BIS,OU=T2,DC=...
    """
    if not dn or not ou_exclues:
        return False
    composants = {c.strip().upper() for c in dn.split(",")}
    return any(f"OU={ou.strip().upper()}" in composants for ou in ou_exclues if ou.strip())


def personne_depuis_attributs(attributs: Dict[str, Any]) -> Optional[PersonneAnnuaire]:
    """Construit une personne a partir des attributs d'une entree ; None sans matricule."""

    def valeur(nom: str) -> Optional[str]:
        brut = attributs.get(nom)
        if isinstance(brut, list):
            brut = brut[0] if brut else None
        texte = str(brut).strip() if brut is not None else ""
        return texte or None

    matricule = valeur("sAMAccountName")
    if matricule is None:
        return None
    prenom, nom = valeur("givenName"), valeur("sn")
    nom_affiche = valeur("displayName") or " ".join(p for p in (prenom, nom) if p) or matricule
    return PersonneAnnuaire(
        matricule=matricule,
        nom_affiche=nom_affiche,
        email=valeur("mail"),
        prenom=prenom,
        nom=nom,
        departement=valeur("department"),
    )


# -- Cadence --------------------------------------------------------------------


class LimiteurRequetes:
    """Une requete au plus toutes les `intervalle` secondes, par cle (matricule).

    En memoire, donc par processus : avec plusieurs workers uvicorn, la limite
    vaut par worker. Elle protege l'AD d'une saisie trop rapide, pas d'un abus
    delibere, ce que la reserve de la recherche aux administrateurs couvre deja.
    """

    def __init__(self, intervalle: float) -> None:
        self.intervalle = intervalle
        self._derniers: Dict[str, float] = {}

    def attente(self, cle: str, maintenant: Optional[float] = None) -> float:
        """Secondes a attendre avant la prochaine requete ; 0 = elle passe, et
        elle est comptee."""
        instant = time.monotonic() if maintenant is None else maintenant
        dernier = self._derniers.get(cle)
        if dernier is not None and instant - dernier < self.intervalle:
            return self.intervalle - (instant - dernier)
        self._derniers[cle] = instant
        return 0.0


# -- Client ldap3 -----------------------------------------------------------------


class AnnuaireLdap:
    """Annuaire Active Directory interroge par ldap3, en LDAPS."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        use_ssl: bool,
        bind_dn: str,
        password: str,
        base_dn: str,
        ca_bundle: str = "",
        timeout_seconds: int = 5,
        limite: int = 25,
        prefixes_exclus: Sequence[str] = (),
        ou_exclues: Sequence[str] = (),
        suffixes_exclus: Sequence[str] = (),
    ) -> None:
        if not (host and bind_dn and password and base_dn):
            raise AnnuaireDesactive(
                "annuaire incomplet : AD_HOST, AD_BIND_DN, AD_PASSWORD et AD_BASE_DN requis"
            )
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.bind_dn = bind_dn
        self._password = password
        self.base_dn = base_dn
        self.ca_bundle = ca_bundle
        self.timeout_seconds = timeout_seconds
        self.limite = limite
        self.prefixes_exclus = [p for p in prefixes_exclus if p.strip()]
        self.suffixes_exclus = [s for s in suffixes_exclus if s.strip()]
        self.ou_exclues = [o for o in ou_exclues if o.strip()]

    def _serveur(self) -> Any:
        import ssl

        from ldap3 import NONE, Server, Tls

        tls = None
        if self.use_ssl:
            tls = Tls(
                validate=ssl.CERT_REQUIRED,
                ca_certs_file=self.ca_bundle or None,
            )
        return Server(
            self.host,
            port=self.port,
            use_ssl=self.use_ssl,
            tls=tls,
            get_info=NONE,
            connect_timeout=self.timeout_seconds,
        )

    def _connexion(self) -> Any:
        from ldap3 import SIMPLE, Connection

        return Connection(
            self._serveur(),
            user=self.bind_dn,
            password=self._password,
            authentication=SIMPLE,
            receive_timeout=self.timeout_seconds,
            read_only=True,
        )

    def _chercher(self, filtre: str, limite: int) -> List[PersonneAnnuaire]:
        from ldap3 import SUBTREE
        from ldap3.core.exceptions import LDAPException

        try:
            connexion = self._connexion()
            if not connexion.bind():
                raise AnnuaireErreur(f"liaison au compte de service refusee : {connexion.result}")
            try:
                connexion.search(
                    self.base_dn,
                    filtre,
                    search_scope=SUBTREE,
                    attributes=ATTRIBUTS,
                    size_limit=limite,
                    time_limit=self.timeout_seconds,
                )
                entrees = [
                    e.get("attributes", {})
                    for e in connexion.response or []
                    if not dans_ou_exclue(e.get("dn"), self.ou_exclues)
                ]
            finally:
                connexion.unbind()
        except LDAPException as exc:
            raise AnnuaireErreur(f"annuaire injoignable : {exc}") from exc
        personnes = [p for p in map(personne_depuis_attributs, entrees) if p is not None]
        return sorted(personnes, key=lambda p: ((p.departement or "~"), p.nom_affiche.lower()))

    async def rechercher(self, texte: str) -> List[PersonneAnnuaire]:
        filtre = filtre_recherche(texte, self.prefixes_exclus, self.suffixes_exclus)
        return await asyncio.to_thread(self._chercher, filtre, self.limite)

    async def trouver(self, matricule: str) -> Optional[PersonneAnnuaire]:
        filtre = filtre_matricule(matricule, self.prefixes_exclus, self.suffixes_exclus)
        trouvees = await asyncio.to_thread(self._chercher, filtre, 2)
        return trouvees[0] if len(trouvees) == 1 else None


def annuaire_depuis_settings(settings: Any) -> AnnuaireLdap:
    """L'annuaire configure ; AnnuaireDesactive s'il est coupe ou incomplet."""
    if not settings.ad_enabled:
        raise AnnuaireDesactive("annuaire desactive (AD_ENABLED=false)")
    return AnnuaireLdap(
        host=settings.ad_host,
        port=settings.ad_port,
        use_ssl=settings.ad_use_ssl,
        bind_dn=settings.ad_bind_dn,
        password=settings.ad_password,
        base_dn=settings.ad_base_dn,
        ca_bundle=settings.ad_ca_bundle,
        timeout_seconds=settings.ad_timeout_seconds,
        limite=settings.ad_search_limit,
        prefixes_exclus=_liste(settings.ad_exclude_prefixes),
        suffixes_exclus=_liste(settings.ad_exclude_suffixes),
        ou_exclues=_liste(settings.ad_exclude_ous),
    )


def _liste(valeur: str) -> List[str]:
    """« OT2, ADM » -> ["OT2", "ADM"] : une liste lisible dans un .env."""
    return [v.strip() for v in (valeur or "").split(",") if v.strip()]
