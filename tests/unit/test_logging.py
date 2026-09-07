import pytest

from adam_core.core.config import CoreSettings
from adam_core.utils.logging import build_log_config, get_logger


def _settings(**overrides: object) -> CoreSettings:
    base: dict[str, object] = {
        "app_env": "dev",
        "app_name": "ADAM",
        "app_version": "0.1.0",
        "postgres_user": "u",
        "postgres_password": "p",
        "postgres_host": "localhost",
        "postgres_port": 5432,
        "postgres_db": "db",
        "log_format": "text",
    }
    base.update(overrides)
    return CoreSettings(**base)  # type: ignore[arg-type]


def test_build_log_config_text() -> None:
    cfg = build_log_config(_settings())
    assert "text" in cfg["formatters"]


class TestBibliothequesBavardes:
    """Le niveau racine ne doit pas rendre httpx et SQLAlchemy bavards.

    Poser LOG_LEVEL=DEBUG pour suivre un worker faisait aussi tracer chaque
    etape de connexion TCP et chaque instruction SQL, BEGIN et COMMIT compris.
    """

    def test_en_debug_les_bibliotheques_restent_a_warning(self) -> None:
        cfg = build_log_config(_settings(log_level="DEBUG"))
        assert cfg["root"]["level"] == "DEBUG"
        assert cfg["loggers"]["httpx"]["level"] == "WARNING"
        assert cfg["loggers"]["sqlalchemy.engine"]["level"] == "WARNING"

    def test_en_info_les_bibliotheques_restent_a_warning(self) -> None:
        cfg = build_log_config(_settings(log_level="INFO"))
        assert cfg["loggers"]["httpcore"]["level"] == "WARNING"

    @pytest.mark.parametrize("level", ["WARNING", "ERROR", "CRITICAL"])
    def test_un_niveau_severe_s_applique_aussi_aux_bibliotheques(self, level: str) -> None:
        # Sinon httpx parlerait plus fort que l'application elle-meme.
        cfg = build_log_config(_settings(log_level=level))
        assert cfg["loggers"]["httpx"]["level"] == level


def test_get_logger() -> None:
    logger = get_logger("test")
    assert logger.name == "test"
