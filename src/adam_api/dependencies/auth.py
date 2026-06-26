"""
Auth - Detection de l'origine de la requete.
"""

import secrets
from typing import Optional, Union

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from adam_api.core.config import settings
from adam_core.utils.logging import get_logger

logger = get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-Internal-Token", auto_error=False)


class UserCaller(BaseModel):
    matricule: str
    organisation_id: int


class ServiceCaller(BaseModel):
    service_name: str


Caller = Union[UserCaller, ServiceCaller]


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
