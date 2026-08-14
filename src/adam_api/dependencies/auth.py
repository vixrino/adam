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

import secrets
from typing import Optional, Union

from fastapi import Depends, HTTPException
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


async def get_caller(
    jwt: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    api_key: Optional[str] = Depends(_api_key_header),
) -> Caller:
    """Detecte l'origine - IHM ou service machine."""
    if api_key is not None:
        if not settings.internal_auth_enabled:
            logger.critical("AUTH SERVICE BYPASS actif ne jamais utiliser en production")
            return ServiceCaller(service_name="bypass-dev")
        if not secrets.compare_digest(api_key, settings.internal_api_key):
            raise HTTPException(status_code=403, detail="Token service invalide")
        return ServiceCaller(service_name="internal-service")
    if jwt is not None:
        if settings.api_disable_jwt_validation:
            logger.critical("JWT BYPASS actif ne jamais utiliser en production")
            return UserCaller(matricule="MAT00003", organisation_id=1)
        raise HTTPException(status_code=501, detail="Auth JWT non implementee")
    raise HTTPException(status_code=401, detail="Authentification requise")


async def require_user(caller: Caller = Depends(get_caller)) -> UserCaller:
    if not isinstance(caller, UserCaller):
        raise HTTPException(status_code=403, detail="Route reservee aux utilisateurs IHM")
    return caller


async def require_service(caller: Caller = Depends(get_caller)) -> ServiceCaller:
    if not isinstance(caller, ServiceCaller):
        raise HTTPException(status_code=403, detail="Route reservee aux services internes")
    return caller
