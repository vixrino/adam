"""Tests unitaires adam_api/routers/admin.py

La route force le consensus d'un document. Elle n'existe que pour le
developpement : hors APP_ENV=dev, elle doit repondre 403 sans rien resoudre.
"""

from typing import Any, Dict, List, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers import admin
from adam_api.routers.admin import router

ROUTE = "/documents/admin/consensus/resolve"


@pytest.fixture(name="appels")
def _appels_fixture(monkeypatch: pytest.MonkeyPatch) -> List[Tuple[int, int]]:
    appels: List[Tuple[int, int]] = []

    async def faux_try_resolve(document_id: int, dataset_id: int) -> Dict[str, Any]:
        appels.append((document_id, dataset_id))
        return {"document_id": document_id, "status": "VALIDATED", "resolus": 3}

    monkeypatch.setattr(admin, "try_resolve", faux_try_resolve)
    return appels


@pytest.fixture(name="client")
def _client_fixture() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def _env(monkeypatch: pytest.MonkeyPatch, app_env: str) -> None:
    monkeypatch.setattr(admin.settings, "app_env", app_env)


@pytest.mark.parametrize("app_env", ["prod", "recette", "DEV-like", ""])
def test_hors_dev_la_route_refuse_sans_resoudre(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, appels: List[Any], app_env: str
) -> None:
    _env(monkeypatch, app_env)

    reponse = client.post(f"{ROUTE}/12", params={"dataset_id": 3})

    assert reponse.status_code == 403
    assert not appels


@pytest.mark.parametrize("app_env", ["dev", "DEV"])
def test_en_dev_la_route_resout_et_rend_le_resultat(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, appels: List[Any], app_env: str
) -> None:
    _env(monkeypatch, app_env)

    reponse = client.post(f"{ROUTE}/12", params={"dataset_id": 3})

    assert reponse.status_code == 200
    assert reponse.json() == {"document_id": 12, "status": "VALIDATED", "resolus": 3}
    assert appels == [(12, 3)]


def test_dataset_id_est_obligatoire(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, appels: List[Any]
) -> None:
    _env(monkeypatch, "dev")

    reponse = client.post(f"{ROUTE}/12")

    assert reponse.status_code == 422
    assert not appels
