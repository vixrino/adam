from adam_core.core.config import CoreSettings
from adam_core.utils.logging import build_log_config, get_logger


def test_build_log_config_text() -> None:
    settings = CoreSettings(
        app_env="dev",
        app_name="ADAM",
        app_version="0.1.0",
        postgres_user="u",
        postgres_password="p",
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="db",
        log_format="text",
    )
    cfg = build_log_config(settings)
    assert "text" in cfg["formatters"]


def test_get_logger() -> None:
    logger = get_logger("test")
    assert logger.name == "test"
