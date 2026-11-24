"""Le message de configuration manquante ne doit pas supposer un fichier .env.

Le deploiement exporte les variables juste avant le lancement, sans fichier .env : dire
« absentes du .env » envoie chercher un fichier qui n'existe pas.
"""

import pytest

from adam_api.core import config as api_config
from adam_core.core import config as core_config


def _without_env_file(monkeypatch: pytest.MonkeyPatch, module: object, class_name: str) -> None:
    """La classe de settings, lue sans .env et sans aucune variable : tout est manquant."""
    real = getattr(module, class_name)
    for field in real.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)
    monkeypatch.setattr(module, class_name, lambda: real(_env_file=None))


@pytest.mark.parametrize(
    ("module", "class_name", "getter"),
    [
        (core_config, "CoreSettings", core_config.get_core_settings),
        (api_config, "Settings", api_config.get_settings),
    ],
    ids=["core", "api"],
)
def test_missing_variables_do_not_blame_the_env_file(
    monkeypatch: pytest.MonkeyPatch, module: object, class_name: str, getter: object
) -> None:
    _without_env_file(monkeypatch, module, class_name)

    with pytest.raises(RuntimeError) as exc:
        getter.__wrapped__()  # type: ignore[attr-defined]

    message = str(exc.value)
    assert "Variables d'environnement absentes" in message
    assert "APP_ENV" in message.upper()  # the missing variables are listed


@pytest.mark.parametrize(
    ("module", "class_name", "getter"),
    [
        (core_config, "CoreSettings", core_config.get_core_settings),
        (api_config, "Settings", api_config.get_settings),
    ],
    ids=["core", "api"],
)
def test_the_message_never_prints_a_secret(
    monkeypatch: pytest.MonkeyPatch, module: object, class_name: str, getter: object
) -> None:
    """Les valeurs fournies ne doivent jamais apparaitre, seulement les noms manquants."""
    _without_env_file(monkeypatch, module, class_name)
    monkeypatch.setenv("POSTGRES_PASSWORD", "ne-doit-pas-apparaitre")

    with pytest.raises(RuntimeError) as exc:
        getter.__wrapped__()  # type: ignore[attr-defined]

    assert "ne-doit-pas-apparaitre" not in str(exc.value)
    assert "ne-doit-pas-apparaitre" not in str(exc.value.__cause__)
