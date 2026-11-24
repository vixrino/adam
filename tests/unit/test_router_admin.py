"""Tests unitaires adam_api/routers/admin.py"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from adam_api.dependencies.auth import ServiceCaller, UserCaller, get_caller
from adam_api.dependencies.db import get_db
from adam_api.routers.admin import KNOWN_SETTINGS, router
from adam_core.enums.roles import PlatformRole

_NOW = datetime(2026, 11, 18, 9, 0, tzinfo=timezone.utc)
_ADMIN = UserCaller(
    matricule="MAT00003", organisation_id=1, platform_role=PlatformRole.NOTA_ADMIN.value
)


def _ligne(key, value, by="MAT00003"):
    return MagicMock(key=key, value=value, updated_at=_NOW, updated_by=by)


@pytest.fixture
def db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(db):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_caller] = lambda: _ADMIN
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "caller",
    [
        UserCaller(
            matricule="M", organisation_id=1, platform_role=PlatformRole.NOTA_SUPERVISOR.value
        ),
        UserCaller(matricule="M", organisation_id=1),
        ServiceCaller(service_name="worker"),
    ],
)
@pytest.mark.parametrize(
    "method,url",
    [
        ("get", "/api/v1/admin/settings"),
        ("put", "/api/v1/admin/settings/x"),
        ("delete", "/api/v1/admin/settings/x"),
        ("get", "/api/v1/admin/env"),
        ("post", "/api/v1/admin/consensus/resolve/1?dataset_id=1"),
    ],
)
def test_non_admin_forbidden(client, caller, method, url):
    client.app.dependency_overrides[get_caller] = lambda: caller
    assert client.request(method.upper(), url, json={"value": 1}).status_code == 403


def test_list_merges_rows_and_known_keys(client, db):
    with patch(
        "adam_api.routers.admin.settings_store.rows",
        AsyncMock(return_value=[_ligne("ocr_enabled", False), _ligne("custom", {"a": 1})]),
    ):
        corps = client.get("/api/v1/admin/settings").json()
    par_cle = {s["key"]: s for s in corps}
    assert set(par_cle) == {"custom", *KNOWN_SETTINGS}
    assert par_cle["ocr_enabled"]["source"] == "db"
    assert par_cle["ocr_enabled"]["effective"] is False
    assert par_cle["ocr_enabled"]["updated_by"] == "MAT00003"
    assert par_cle["ad_enabled"]["source"] == "default"
    assert par_cle["ad_enabled"]["effective"] is False
    assert par_cle["ad_enabled"]["updated_at"] is None
    assert par_cle["ocr_status"]["managed_by_worker"] is True
    assert par_cle["custom"]["default"] is None


def test_ad_enabled_forced_by_env(client):
    with (
        patch("adam_api.routers.admin.settings_store.rows", AsyncMock(return_value=[])),
        patch("adam_api.routers.admin.settings") as cfg,
    ):
        cfg.ad_enabled = True
        corps = client.get("/api/v1/admin/settings").json()
    ad = next(s for s in corps if s["key"] == "ad_enabled")
    assert (ad["source"], ad["effective"]) == ("env", True)


def test_put_sets_updated_by_from_caller(client, db):
    ligne = _ligne("worker.ConsensusWorker.poll_interval", 12)
    with (
        patch("adam_api.routers.admin.settings_store.load", AsyncMock(return_value={})),
        patch("adam_api.routers.admin.settings_store.set_value", AsyncMock()) as ecrire,
        patch("adam_api.routers.admin.settings_store.rows", AsyncMock(return_value=[ligne])),
    ):
        r = client.put(
            "/api/v1/admin/settings/worker.ConsensusWorker.poll_interval", json={"value": 12}
        )
    assert r.status_code == 200
    assert r.json()["effective"] == 12
    assert ecrire.await_args.kwargs["updated_by"] == "MAT00003"
    db.commit.assert_awaited()


@pytest.mark.parametrize(
    "key,value",
    [
        ("ocr_enabled", "oui"),
        ("ocr_enabled", 1),
        ("worker.ConsensusWorker.poll_interval", 0),
        ("worker.ConsensusWorker.poll_interval", True),
        ("worker.ConsensusWorker.poll_interval", "5"),
        ("custom", None),
        ("custom", "x" * 11_000),
        ("bad key!", 1),
    ],
)
def test_put_rejects_invalid(client, key, value):
    assert client.put(f"/api/v1/admin/settings/{key}", json={"value": value}).status_code == 422


def test_put_unknown_key_accepts_any_json(client):
    with (
        patch("adam_api.routers.admin.settings_store.load", AsyncMock(return_value={})),
        patch("adam_api.routers.admin.settings_store.set_value", AsyncMock()),
        patch(
            "adam_api.routers.admin.settings_store.rows",
            AsyncMock(return_value=[_ligne("x", [1, "a"])]),
        ),
    ):
        r = client.put("/api/v1/admin/settings/x", json={"value": [1, "a"]})
    assert r.status_code == 200 and r.json()["value"] == [1, "a"]


def test_delete(client, db):
    with patch("adam_api.routers.admin.settings_store.delete", AsyncMock(return_value=True)):
        assert client.delete("/api/v1/admin/settings/x").status_code == 204
    db.commit.assert_awaited()
    with patch("adam_api.routers.admin.settings_store.delete", AsyncMock(return_value=False)):
        assert client.delete("/api/v1/admin/settings/x").status_code == 404


def test_env_masks_secrets(client):
    from adam_api.core.config import settings

    corps = client.get("/api/v1/admin/env").json()
    par_nom = {v["name"]: v for v in corps}
    assert par_nom["APP_ENV"]["value"] is not None
    secrets = [v for v in corps if v["secret"]]
    assert {"POSTGRES_PASSWORD", "INTERNAL_API_KEY", "MISTRAL_API_KEY", "AD_PASSWORD"} <= {
        v["name"] for v in secrets
    }
    assert all(v["value"] is None for v in secrets)
    with patch.object(type(settings), "mistral_api_key", "s3cr3t-unique-xyz", create=True):
        assert "s3cr3t-unique-xyz" not in client.get("/api/v1/admin/env").text


def test_known_worker_defaults_match_the_workers():
    from adam_worker.base_worker import BaseWorker
    from adam_worker.benchmark.worker import TestExecutionWorker
    from adam_worker.consensus_worker import ConsensusWorker
    from adam_worker.page_image_worker import PageImageWorker
    from adam_worker.prepopulation.poller import PrepopulationWorker

    for w in (PageImageWorker, ConsensusWorker, PrepopulationWorker, TestExecutionWorker):
        assert (
            KNOWN_SETTINGS[f"worker.{w.__name__}.poll_interval"]["default"]
            == w.poll_interval_seconds
        )
    assert BaseWorker.poll_interval_seconds == 5.0


def test_settings_store_delete_and_rows():
    import asyncio

    from adam_core.db import settings_store

    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=1)
    assert asyncio.run(settings_store.delete(db, "k")) is True
    db.execute.return_value = MagicMock(rowcount=0)
    assert asyncio.run(settings_store.delete(db, "k")) is False
