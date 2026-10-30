"""
Settings transverses partagees par tous les packages NOTA.
Heriter de CoreSettings pour ajouter des settings specifiques.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

ROOT_DIR = Path(__file__).resolve().parents[3]


class CoreSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # La config porte des secrets : jamais dans un message d'erreur ni dans le traceback de
        # demarrage (get_core_settings chaine l'exception d'origine, dont l'entree figure).
        hide_input_in_errors=True,
    )

    # App
    app_env: str
    app_name: str
    app_version: str

    # PostgreSQL
    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int
    postgres_db: str

    # Logging
    log_level: str = Field(default="DEBUG")
    log_format: str = Field(default="text")

    # Computed
    @property
    def is_dev(self) -> bool:
        return self.app_env.lower() == "dev"

    @property
    def async_database_url(self) -> str:
        return str(
            URL.create(
                drivername="postgresql+asyncpg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                database=self.postgres_db,
            ).render_as_string(hide_password=False)
        )


@lru_cache
def get_core_settings() -> CoreSettings:
    try:
        return CoreSettings()  # type: ignore[call-arg]
    except ValidationError as e:
        missing = [str(err["loc"][0]) for err in e.errors() if err["type"] == "missing"]
        raise RuntimeError(
            "\n\n"
            "  NOTA configuration manquante\n"
            f"  Variables d'environnement absentes : {', '.join(missing)}\n"
            "  Référence : resources/config/.env.template\n"
        ) from e
    # return CoreSettings()  # type: ignore[call-arg]


# core_settings = get_core_settings()
