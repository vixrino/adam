"""
Settings specifiques a l'API ADAM.
"""

from functools import lru_cache
from typing import List

from adam_core.core.config import CoreSettings


class Settings(CoreSettings):
    api_host: str
    api_port: int
    api_version: str
    api_title: str
    api_cors_origins: str
    api_disable_jwt_validation: bool
    internal_auth_enabled: bool
    internal_api_key: str
    pvc_mount_path: str
    ocr_mock_enabled: bool
    ocr_mock_confidence: float
    ocr_timeout_seconds: int

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.api_cors_origins.split(",")]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
