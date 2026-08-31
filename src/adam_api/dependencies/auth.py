"""
Auth - Detection de l'origine de la requete.

FBI authentifie, la base autorise
---------------------------------
Le token BdF porte l'identite de l'agent et rien d'autre : son `principal`, qui
a la forme d'un matricule. Ni l'organisation ni le role de plateforme n'y
figurent, et c'est logique — FBI connait les agents de la Banque, pas le decoupage
metier de nota. Les deux sont donc lus dans la table `user`, dont le matricule
est la seule cle de jointure avec le token.

Il en decoule une distinction a ne pas rater : un agent connu de FBI mais absent
de `user` recoit un 403, pas un 401. Son token est valide, il n'est simplement pas
utilisateur de l'application. Repondre 401 enverrait les gens ouvrir un ticket SSO
pour un probleme d'habilitation applicative.

Deux vocabulaires de roles coexistent
--------------------------------------
`conf/pie.yaml` filtre les URI sur ADMIN|SUPERVISOR|OPERATOR : un grillage
grossier, « ce matricule a-t-il le droit de toucher /documents du tout ». Ce
n'est PAS le modele de roles de l'application, qui en compte cinq repartis en
ProjectRole et PlatformRole, et dont le premier depend du projet — une notion
qu'un fichier de configuration d'URI ne peut pas exprimer.

Les deux restent donc separes, et le controle fin appartient a l'API. Confondre
les deux mettrait la moitie de l'autorisation dans un YAML et l'autre en base.
"""

import base64
import json
import secrets
from typing import Any, Optional, Union

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import func, select

from adam_api.core.config import settings
from adam_core.db.session import get_async_session
from adam_core.enums.status import UserStatus
from adam_core.models import User
from adam_core.utils.logging import get_logger

logger = get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-Internal-Token", auto_error=False)


class UserCaller(BaseModel):
    matricule: str
    organisation_id: int
    # Role transverse (PlatformRole) ou None pour un utilisateur purement metier.
    # Renseigne, il neutralise le filtrage par organisation : cf. dependencies.db.
    platform_role: Optional[str] = None


class ServiceCaller(BaseModel):
    service_name: str


Caller = Union[UserCaller, ServiceCaller]

#: Claims susceptibles de porter le matricule, par ordre de preference.
#:
#: Le token du mock en porte quatre, et ils ne s'accordent pas entre eux : `sub`,
#: `prn` et `user_name` rendent I659418, `uid` rend i659418. Aucun standard
#: n'impose lequel un fournisseur renseigne, d'ou cette liste plutot qu'un nom
#: unique — le vrai FBI n'est pas tenu de se comporter comme son bouchon.
#:
#: `sub` d'abord : c'est le sujet au sens de la RFC 7519, present chez tout
#: emetteur conforme. `prn` ensuite, convention Oracle dont le mock imite les
#: claims (`oracle.oauth.*`). `user_name` en dernier, convention Spring OAuth2.
#: `uid` est volontairement absent : il porte la casse saisie par l'agent, la
#: comparaison en base etant de toute facon insensible a la casse.
PRINCIPAL_CLAIMS = ("sub", "prn", "user_name")


def principal_from_claims(claims: dict[str, Any]) -> str:
    """Extrait le matricule des claims d'un token deja valide.

    Args:
        claims: la charge utile du JWT, telle que le middleware l'a validee.

    Returns:
        Le premier claim non vide de PRINCIPAL_CLAIMS.

    Raises:
        HTTPException: 401 si aucun ne porte de valeur exploitable. Contrairement
            aux refus de resolve_caller, celui-ci est bien un 401 : un token sans
            sujet n'identifie personne, il n'y a pas d'habilitation a discuter.
    """
    for claim in PRINCIPAL_CLAIMS:
        value = claims.get(claim)
        if isinstance(value, str) and value.strip():
            logger.debug("principal lu depuis le claim %s", claim)
            return value.strip()

    logger.error(
        "token valide mais sans claim de sujet exploitable [claims=%s]",
        sorted(claims),  # les noms seulement, jamais les valeurs
    )
    raise HTTPException(status_code=401, detail="Token sans identifiant d'utilisateur")


async def resolve_caller(principal: str) -> UserCaller:
    """Construit le caller a partir du `principal` porte par le token.

    Le matricule est compare en majuscules : le mock FBI accepte `i659418` comme
    nom de fichier utilisateur tout en rendant `I659418` en principal, et rien ne
    garantit que le vrai FBI soit plus regulier. Une comparaison sensible a la
    casse ferait dependre l'authentification de la facon dont l'agent a tape son
    identifiant.

    La session est ouverte SANS scope. C'est necessaire et non un oubli : le
    filtrage derive du caller, on ne peut donc pas l'appliquer pour le resoudre.
    La requete est bornee a une lecture de `user` par matricule, ce qui ne
    divulgue rien — l'appelant apprend sa propre organisation.

    Raises:
        HTTPException: 403 si le matricule est inconnu de `user` ou si le compte
            n'est pas actif. Jamais 401 : le token est valide, cf. docstring du
            module.
    """
    async with get_async_session() as session:
        row = (
            await session.execute(
                select(User.matricule, User.organisation_id, User.platform_role, User.status).where(
                    func.upper(User.matricule) == principal.strip().upper()
                )
            )
        ).one_or_none()

    if row is None:
        # Le matricule n'est pas logue en clair : il identifie une personne, et
        # ce chemin est atteignable par n'importe quel agent de la Banque.
        logger.warning("principal authentifie mais inconnu de la table user")
        raise HTTPException(status_code=403, detail="Compte non habilite sur cette application")

    if row.status != UserStatus.ACTIVE.value:
        logger.warning("compte non actif [status=%s]", row.status)
        raise HTTPException(status_code=403, detail="Compte inactif ou suspendu")

    return UserCaller(
        matricule=str(row.matricule),
        organisation_id=int(row.organisation_id),
        platform_role=row.platform_role,
    )


def _payload_of(token: str) -> Optional[dict[str, Any]]:
    """Charge utile d'un JWT, sans verifier la signature.

    Ne jamais appeler sur un token non valide en amont : cette fonction lit, elle
    ne controle rien. Le seul appelant est claims_from_request, qui n'est atteint
    que derriere le middleware.
    """
    if token.count(".") != 2:
        return None
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, UnicodeDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def claims_from_request(request: Request) -> dict[str, Any]:
    """Claims du token, une fois exa-pie passe.

    Trois sources, dans l'ordre. Les deux premieres exploitent ce que le
    middleware pose ; la troisieme relit l'en-tete, et c'est en pratique celle
    qui sert.

    Pourquoi pie_token n'arrive pas jusqu'ici
    ------------------------------------------
    Le middleware fait `setattr(request, 'pie_token', token)` sur SON objet
    Request. `call_next` ne transmet ensuite que le scope ASGI, a partir duquel
    FastAPI reconstruit un nouveau Request pour la route : un attribut pose a la
    main sur le premier objet ne suit pas. Seul `request.state` traverse, parce
    qu'il ecrit dans le scope partage — ce que le connecteur ne fait pas.

    Les deux premieres sources sont conservees malgre tout : elles coutent deux
    getattr, et une version ulterieure d'exa-pie pourrait passer par le scope.

    Relire l'en-tete n'est pas un contournement
    --------------------------------------------
    Cette fonction n'est atteinte que si `verify` a rendu 200 : sinon le
    middleware a deja repondu 400 ou 401, et la dependance n'est jamais appelee.
    La signature est donc verifiee en amont, et il ne reste qu'a lire ce qu'elle
    protege. Le bypass DEV, lui, n'appelle jamais cette fonction — c'est ce qui
    empeche un token fabrique a la main de passer quand rien ne le verifie.

    Raises:
        HTTPException: 401 si aucune source n'est exploitable.
    """
    context = getattr(request, "pie_context", None)
    if isinstance(context, dict) and context:
        return context

    for token in (getattr(request, "pie_token", None), _bearer_header(request)):
        if isinstance(token, str):
            claims = _payload_of(token)
            if claims:
                return claims

    logger.error("aucune source de claims exploitable : en-tete absent ou token illisible")
    raise HTTPException(status_code=401, detail="Contexte d'authentification indisponible")


def _bearer_header(request: Request) -> Optional[str]:
    """Token porte par l'en-tete Authorization, ou None."""
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value.strip() else None


async def get_caller(
    request: Request,
    jwt: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    api_key: Optional[str] = Depends(_api_key_header),
) -> Caller:
    """Detecte l'origine - IHM ou service machine.

    Le bypass DEV ne lit PAS le token
    ----------------------------------
    Quand api_disable_jwt_validation est actif, le middleware n'est pas monte et
    aucune signature n'est verifiee. Lire le token dans ce mode reviendrait a
    faire confiance a un JWT fabrique a la main : n'importe qui posant
    `"sub": "<un matricule d'administrateur>"` obtiendrait ses droits. Le bypass
    endosse donc un matricule fixe, celui de la configuration, et ignore
    entierement l'en-tete Authorization.

    Il passe malgre tout par resolve_caller, donc par la base. L'ancienne version
    fabriquait un UserCaller de toutes pieces, avec un organisation_id=1 qui ne
    correspondait a aucune ligne reelle : le perimetre observe en DEV n'etait
    celui de personne, et tester le cloisonnement etait impossible.
    """
    if api_key is not None:
        if not settings.internal_auth_enabled:
            logger.critical("AUTH SERVICE BYPASS actif ne jamais utiliser en production")
            return ServiceCaller(service_name="bypass-dev")
        if not secrets.compare_digest(api_key, settings.internal_api_key):
            raise HTTPException(status_code=403, detail="Token service invalide")
        return ServiceCaller(service_name="internal-service")

    if settings.api_disable_jwt_validation:
        logger.critical(
            "JWT BYPASS actif : appel endosse par %s sans aucune verification. "
            "Ne jamais utiliser en production.",
            settings.api_dev_matricule,
        )
        return await resolve_caller(settings.api_dev_matricule)

    if jwt is None:
        raise HTTPException(status_code=401, detail="Authentification requise")

    return await resolve_caller(principal_from_claims(claims_from_request(request)))


async def require_user(caller: Caller = Depends(get_caller)) -> UserCaller:
    if not isinstance(caller, UserCaller):
        raise HTTPException(status_code=403, detail="Route reservee aux utilisateurs IHM")
    return caller


async def require_service(caller: Caller = Depends(get_caller)) -> ServiceCaller:
    if not isinstance(caller, ServiceCaller):
        raise HTTPException(status_code=403, detail="Route reservee aux services internes")
    return caller
