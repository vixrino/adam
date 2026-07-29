"""
Tests unitaires adam_api/core/security.py

exa_pie n'est disponible que sur le Pypi interne : un faux module est injecte
dans sys.modules pour verifier le montage sans dependre de son installation.
"""

import sys
import types
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from adam_api.core import security
from adam_api.core.security import install_jwt_middleware

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakePIEMiddleware(BaseHTTPMiddleware):
    """Tient lieu de PIEFastAPIMiddleware pendant les tests."""


@pytest.fixture
def fake_exa_pie() -> Iterator[None]:
    """Injecte un faux exa_pie.middleware.fastapi dans sys.modules."""
    root = types.ModuleType("exa_pie")
    middleware_pkg = types.ModuleType("exa_pie.middleware")
    fastapi_mod = types.ModuleType("exa_pie.middleware.fastapi")
    fastapi_mod.PIEFastAPIMiddleware = FakePIEMiddleware  # type: ignore[attr-defined]

    injected = {
        "exa_pie": root,
        "exa_pie.middleware": middleware_pkg,
        "exa_pie.middleware.fastapi": fastapi_mod,
    }
    sys.modules.update(injected)
    try:
        yield
    finally:
        for name in injected:
            sys.modules.pop(name, None)


@pytest.fixture
def app() -> FastAPI:
    return FastAPI()


def _set_bypass(monkeypatch: pytest.MonkeyPatch, value: bool) -> None:
    """Positionne le bypass DEV sur l'instance de settings partagee."""
    monkeypatch.setattr(security.settings, "api_disable_jwt_validation", value)


def _middleware_classes(app: FastAPI) -> list[type]:
    """Classes de middlewares, de la plus externe a la plus interne."""
    return [m.cls for m in app.user_middleware]


# ---------------------------------------------------------------------------
# Bypass DEV
# ---------------------------------------------------------------------------


def test_bypass_actif_ne_monte_pas_le_middleware(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_bypass(monkeypatch, True)

    assert install_jwt_middleware(app) is False
    assert app.user_middleware == []


def test_bypass_actif_n_importe_pas_exa_pie(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """Le bypass doit permettre de demarrer sans le connecteur installe."""
    _set_bypass(monkeypatch, True)
    for name in [m for m in sys.modules if m.startswith("exa_pie")]:
        monkeypatch.delitem(sys.modules, name, raising=False)

    install_jwt_middleware(app)

    assert not [m for m in sys.modules if m.startswith("exa_pie")]


def test_bypass_actif_journalise_une_alerte(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _set_bypass(monkeypatch, True)

    with caplog.at_level("CRITICAL"):
        install_jwt_middleware(app)

    assert "JWT BYPASS actif" in caplog.text


# ---------------------------------------------------------------------------
# Validation active
# ---------------------------------------------------------------------------


def test_validation_active_monte_le_middleware(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, fake_exa_pie: None
) -> None:
    _set_bypass(monkeypatch, False)

    assert install_jwt_middleware(app) is True
    assert _middleware_classes(app) == [FakePIEMiddleware]


def test_cors_reste_le_middleware_le_plus_externe(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, fake_exa_pie: None
) -> None:
    """Regression : exa-pie place avant CORS rejetterait les preflights OPTIONS.

    Starlette insere chaque middleware en tete de pile, donc user_middleware[0]
    est le plus externe. CORS, ajoute en dernier comme dans main.py, doit s'y
    trouver.
    """
    _set_bypass(monkeypatch, False)

    install_jwt_middleware(app)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:4200"])

    assert _middleware_classes(app) == [CORSMiddleware, FakePIEMiddleware]


def test_echec_explicite_si_le_connecteur_est_absent(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans bypass et sans connecteur, l'echec est immediat plutot que silencieux.

    L'absence est simulee en neutralisant l'entree sys.modules : importer un
    module associe a None leve ImportError. Le test vaut donc que exa-pie soit
    installe ou non dans l'environnement, ce qui n'etait pas le cas en se
    reposant sur son absence reelle.
    """
    _set_bypass(monkeypatch, False)
    monkeypatch.setitem(sys.modules, "exa_pie.middleware.fastapi", None)

    with pytest.raises(ImportError):
        install_jwt_middleware(app)

    assert app.user_middleware == []
