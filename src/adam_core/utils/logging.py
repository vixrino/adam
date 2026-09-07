from __future__ import annotations

import logging
from logging import config as logging_config
from typing import Any

from adam_core.core.config import CoreSettings

try:
    from exa.logger.formatter import \
        JsonFormatter  # type: ignore[import-untyped]

    _JSON_CLASS = "exa.logger.formatter.JsonFormatter"
except ImportError:
    _JSON_CLASS = "stubs.exa_logger.formatter.JsonFormatter"

_FORMATTERS_JSON = {"json": {"()": _JSON_CLASS}}

_FORMATTERS_TEXT = {
    "text": {
        "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        "datefmt": "%Y-%m-%d %H:%M:%S",
    }
}


#: Bibliotheques dont le journal en DEBUG noie celui de l'application.
#:
#: Le niveau racine s'applique a tout logger sans configuration propre. Poser
#: LOG_LEVEL=DEBUG pour suivre un worker faisait donc aussi parler httpx, qui
#: trace chaque etape de chaque connexion TCP, et l'echo SQLAlchemy, qui imprime
#: chaque instruction emise. Les lignes du worker — quel document, quel echec —
#: se perdaient au milieu.
#:
#: Ces loggers ne sont pas coupes : ils restent au niveau racine des que celui-ci
#: est deja WARNING ou plus severe, et redeviennent verbeux en les nommant
#: explicitement dans une configuration locale le jour ou l'on debogue le
#: transport lui-meme.
_NOISY_LIBRARIES = (
    "httpx",
    "httpcore",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "asyncio",
    "watchfiles",
    "multipart",
)

_LEVEL_ORDER = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


def _library_level(root_level: str) -> str:
    """Niveau des bibliotheques tierces : jamais plus bavard que WARNING.

    Rendre le niveau racine quand il est deja severe evite l'effet inverse — un
    LOG_LEVEL=ERROR qui laisserait passer les avertissements de httpx alors que
    l'application, elle, se tait.
    """
    if _LEVEL_ORDER.get(root_level, 20) >= _LEVEL_ORDER["WARNING"]:
        return root_level
    return "WARNING"


def build_log_config(settings: CoreSettings) -> dict[str, Any]:
    """Construit le dictConfig logging sans l'appliquer."""
    use_json = settings.log_format.lower() == "json"
    root_level = settings.log_level.upper()
    library_level = _library_level(root_level)
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "loggers": {name: {"level": library_level} for name in _NOISY_LIBRARIES},
        "root": {"handlers": ["console"], "level": root_level},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json" if use_json else "text",
            }
        },
        "formatters": _FORMATTERS_JSON if use_json else _FORMATTERS_TEXT,
    }


def setup_logging(settings: CoreSettings) -> None:
    """Applique le dictConfig logging."""
    logging_config.dictConfig(build_log_config(settings))


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger standard pour le module appelant."""
    return logging.getLogger(name)
