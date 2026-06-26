"""Exceptions HTTP standardisees et handler unifie pour FastAPI."""

import logging
from typing import Any, NoReturn, Optional, Type, cast

from fastapi import Request
from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse

from adam_core.utils.logging import get_logger

logger = get_logger(__name__)


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handler unifie logue toutes les erreurs HTTP avec contexte."""
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
    return JSONResponse(status_code=http_exc.status_code, content={"detail": http_exc.detail})


NOT_FOUND = "{} introuvable"
ALREADY_ARCHIVED = "{} deja archive"
NOT_ARCHIVED = "{} non archive"
ALREADY_EXISTS = "{} deja existant"
CONFLICT = "{} : {}"


def _name(model: Type[Any]) -> str:
    name = getattr(model, "__tablename__", model.__name__)
    return name.capitalize()


def raise_not_found(model: Type[Any], detail: Optional[str] = None) -> NoReturn:
    raise HTTPException(status_code=404, detail=detail if detail else NOT_FOUND.format(_name(model)))


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
