"""Hors DEV : pas de bypass d'authentification, et une INTERNAL_API_KEY d'au moins 32 caracteres."""

import pytest
from pydantic import ValidationError

from adam_api.core import config as api_config
from adam_api.core.config import Settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "app_env": "prod",
        "api_disable_jwt_validation": False,
        "internal_auth_enabled": True,
        "internal_api_key": "k" * 32,
    }
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


def test_prod_with_validation_on_is_accepted() -> None:
    assert _settings().app_env == "prod"


@pytest.mark.parametrize("env", ["dev", "DEV", "test"])
def test_bypass_is_accepted_in_dev_and_test(env: str) -> None:
    s = _settings(app_env=env, api_disable_jwt_validation=True, internal_auth_enabled=False)
    assert s.api_disable_jwt_validation is True


@pytest.mark.parametrize(
    "overrides",
    [{"api_disable_jwt_validation": True}, {"internal_auth_enabled": False}],
    ids=["jwt-bypass", "internal-auth-bypass"],
)
@pytest.mark.parametrize("env", ["prod", "int", "integration"])
def test_bypass_is_refused_outside_dev(env: str, overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError, match="bypass d'authentification interdit"):
        _settings(app_env=env, **overrides)


@pytest.mark.parametrize("env", ["prod", "production"])
def test_short_internal_api_key_is_refused_outside_dev(env: str) -> None:
    with pytest.raises(ValidationError, match="INTERNAL_API_KEY trop courte"):
        _settings(app_env=env, internal_api_key="k" * 31)


def test_internal_api_key_of_32_chars_is_accepted_outside_dev() -> None:
    assert len(_settings(internal_api_key="k" * 32).internal_api_key) == 32


@pytest.mark.parametrize("env", ["dev", "test"])
def test_short_internal_api_key_is_accepted_in_dev_and_test(env: str) -> None:
    assert _settings(app_env=env, internal_api_key="abc").internal_api_key == "abc"


def test_the_error_does_not_leak_the_key() -> None:
    with pytest.raises(ValidationError) as exc:
        _settings(internal_api_key="secret-too-short")
    assert "secret-too-short" not in str(exc.value)


def test_settings_keep_the_inherited_env_file_config() -> None:
    assert Settings.model_config.get("env_file")


def test_get_settings_explains_the_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("API_DISABLE_JWT_VALIDATION", "true")
    with pytest.raises(RuntimeError, match="configuration refusee.*bypass d'authentification"):
        api_config.get_settings.__wrapped__()
