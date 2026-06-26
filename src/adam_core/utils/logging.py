from __future__ import annotations

import logging
from logging import config as logging_config
from typing import Any

from adam_core.core.config import CoreSettings

try:
    from exa.logger.formatter import JsonFormatter  # type: ignore[import-untyped]

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


def build_log_config(settings: CoreSettings) -> dict[str, Any]:
    """Construit le dictConfig logging sans l'appliquer."""
    use_json = settings.log_format.lower() == "json"
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "root": {"handlers": ["console"], "level": settings.log_level.upper()},
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
