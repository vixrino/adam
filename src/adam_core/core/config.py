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

    # Compte DDL utilise par `launcher.py migrate` (Alembic) quand l'application tourne avec un
    # compte DML seul. Vide : les migrations utilisent POSTGRES_USER / POSTGRES_PASSWORD.
    migration_postgres_user: str = Field(default="")
    migration_postgres_password: str = Field(default="")

    # Pool de connexions (par processus). Budget total = (pool_size + max_overflow) x processus
    # x replicas, a garder sous max_connections : la base est partagee entre applications.
    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    #: Secondes avant recyclage d'une connexion (coupee par un pare-feu ou un proxy inactif).
    db_pool_recycle: int = Field(default=1800, ge=-1)

    # Logging
    log_level: str = Field(default="DEBUG")
    log_format: str = Field(default="text")

    # Computed
    @property
    def engine_options(self) -> dict[str, int]:
        """Options de pool pour init_engine(url, **options)."""
        return {
            "pool_size": self.db_pool_size,
            "max_overflow": self.db_max_overflow,
            "pool_recycle": self.db_pool_recycle,
        }

    @property
    def is_dev(self) -> bool:
        return self.app_env.lower() == "dev"

    @property
    def async_database_url(self) -> str:
        return self._database_url(self.postgres_user, self.postgres_password)

    @property
    def migration_database_url(self) -> str:
        """URL du compte qui migre : MIGRATION_POSTGRES_* si definis, sinon celle de l'application."""
        if self.migration_postgres_user:
            return self._database_url(
                self.migration_postgres_user, self.migration_postgres_password
            )
        return self.async_database_url

    def _database_url(self, user: str, password: str) -> str:
        return str(
            URL.create(
                drivername="postgresql+asyncpg",
                username=user,
                password=password,
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
