"""
Exceptions HTTP standardisees et handler unifie pour FastAPI.
"""

import logging
from typing import Any, Dict, NoReturn, Optional, Type, cast

from fastapi import Request
from fastapi.exceptions import HTTPException, ResponseValidationError
from fastapi.responses import JSONResponse

from adam_core.utils.logging import get_logger

logger = get_logger(__name__)

# Handler middleware


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handler unifie logue toutes les erreurs HTTP avec contexte.
    4xx -> WARNING, 5xx -> ERROR
    """
    http_exc = cast(HTTPException, exc)
    level = logging.WARNING if http_exc.status_code < 500 else logging.ERROR

    logger.log(
        level,
        "HTTP %s - %s %s - %s",
        http_exc.status_code,
        request.method,
        request.url.path,
        http_exc.detail,
    )

    return JSONResponse(
        status_code=http_exc.status_code,
        content={"detail": http_exc.detail},
    )


async def response_validation_handler(request: Request, exc: Exception) -> JSONResponse:
    """La reponse de la route ne passe pas son response_model : bug serveur, 500.

    Logue le champ et le type de chaque erreur, jamais `input` ni le corps : ils
    peuvent porter des donnees metier, et repr() d'un objet ORM expire echoue
    (c'est ce qui rendait l'erreur illisible : « <exception str() failed> »).
    """
    errors = cast(ResponseValidationError, exc).errors()
    fields = [(".".join(str(part) for part in err["loc"]), err["type"]) for err in errors]
    logger.error(
        "HTTP 500 - reponse invalide - %s %s - %s", request.method, request.url.path, fields
    )
    return JSONResponse(status_code=500, content={"detail": "Erreur interne du serveur"})


# Messages templates

NOT_FOUND = "{} introuvable"
ALREADY_ARCHIVED = "{} deja archive"
NOT_ARCHIVED = "{} non archive"
ALREADY_EXISTS = "{} deja existant"
CONFLICT = "{} : {}"


# Helpers


def _name(model: Type[Any]) -> str:
    name = getattr(model, "__tablename__", model.__name__)
    return name.capitalize()


def raise_not_found(model: Type[Any], detail: Optional[str] = None) -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail=detail if detail else NOT_FOUND.format(_name(model)),
    )


def raise_already_archived(model: Type[Any]) -> NoReturn:
    raise HTTPException(status_code=409, detail=ALREADY_ARCHIVED.format(_name(model)))


def raise_not_archived(model: Type[Any]) -> NoReturn:
    raise HTTPException(status_code=409, detail=NOT_ARCHIVED.format(_name(model)))


def raise_already_exists(model: Type[Any]) -> NoReturn:
    raise HTTPException(status_code=409, detail=ALREADY_EXISTS.format(_name(model)))


def raise_conflict(model: Type[Any], detail: str) -> NoReturn:
    raise HTTPException(status_code=409, detail=CONFLICT.format(_name(model), detail))


def raise_unprocessable(detail: str) -> NoReturn:
    raise HTTPException(status_code=422, detail=detail)


def raise_conflict_message(detail: str) -> NoReturn:
    """409 avec un message libre, sans le prefixe « Modele : » de raise_conflict."""
    raise HTTPException(status_code=409, detail=detail)


def raise_forbidden(detail: Optional[str] = None) -> NoReturn:
    raise HTTPException(status_code=403, detail=detail)


def raise_locked(detail: str) -> NoReturn:
    raise HTTPException(status_code=423, detail=detail)


def raise_too_many_requests(detail: str, headers: Optional[Dict[str, str]] = None) -> NoReturn:
    raise HTTPException(status_code=429, detail=detail, headers=headers)


def raise_bad_gateway(detail: str) -> NoReturn:
    raise HTTPException(status_code=502, detail=detail)


def raise_service_unavailable(detail: str) -> NoReturn:
    raise HTTPException(status_code=503, detail=detail)
