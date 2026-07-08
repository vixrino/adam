"""
Settings transverses partagees par tous les packages ADAM.
Heriter de CoreSettings pour ajouter des settings specifiques.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class CoreSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
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

    @property
    def is_dev(self) -> bool:
        return self.app_env.lower() == "dev"

    @property
    def async_database_url(self) -> str:
        # str(URL) masque le mot de passe (rendu "***") depuis SQLAlchemy 2.x ;
        # il faut render_as_string(hide_password=False) pour obtenir une URL
        # de connexion utilisable par asyncpg.
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)


@lru_cache
def get_core_settings() -> CoreSettings:
    return CoreSettings()  # type: ignore[call-arg]


core_settings = get_core_settings()
