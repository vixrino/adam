"""Tests unitaires adam_api/routers/organisations.py"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.organisations import router


@pytest.fixture
def app() -> FastAPI:
    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    return fastapi_app


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result
    db.get.return_value = None
    return db


@pytest.fixture
def client(app: FastAPI, mock_db: AsyncMock) -> TestClient:
    from adam_api.dependencies.db import get_db
    app.dependency_overrides[get_db] = lambda: mock_db
    return TestClient(app, raise_server_exceptions=False)


def _make_org(id: int = 1, name: str = "Org", slug: str = "org", deleted_at: None = None) -> MagicMock:
    row = MagicMock()
    row.id = id
    row.name = name
    row.slug = slug
    row.deleted_at = deleted_at
    return row


def _make_user(id: int = 1, email: str = "u@example.com", matricule: str = "M001") -> MagicMock:
    row = MagicMock()
    row.id = id
    row.email = email
    row.matricule = matricule
    return row


# ---------------------------------------------------------------------------
# GET /organisations
# ---------------------------------------------------------------------------

class TestListOrganisations:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/organisations").status_code == 200

    def test_returns_empty_list(self, client: TestClient) -> None:
        assert client.get("/organisations").json() == []

    def test_returns_list(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_org(id=1, name="BDF", slug="bdf"),
            _make_org(id=2, name="CAF", slug="caf"),
        ]
        data = client.get("/organisations").json()
        assert len(data) == 2
        assert data[0]["slug"] == "bdf"

    def test_response_contains_expected_fields(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_org(id=5)]
        data = client.get("/organisations").json()
        assert {"id", "name", "slug"} <= data[0].keys()


# ---------------------------------------------------------------------------
# GET /organisations/{org_id}/users
# ---------------------------------------------------------------------------

class TestListOrgUsers:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/organisations/1/users").status_code == 200

    def test_returns_list(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_user(id=1, email="a@x.com", matricule="A1"),
        ]
        data = client.get("/organisations/1/users").json()
        assert data[0]["email"] == "a@x.com"
        assert data[0]["matricule"] == "A1"


# ---------------------------------------------------------------------------
# POST /organisations
# ---------------------------------------------------------------------------

class TestCreateOrganisation:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        org = _make_org(id=1, name="Nouvel Org", slug="nouvel-org")
        mock_db.flush = AsyncMock()
        mock_db.add = MagicMock(side_effect=lambda row: setattr(row, "id", 1))
        resp = client.post("/organisations", json={"name": "Nouvel Org", "slug": "nouvel-org"})
        assert resp.status_code == 201

    def test_422_on_invalid_slug(self, client: TestClient) -> None:
        resp = client.post("/organisations", json={"name": "Org", "slug": "INVALID SLUG"})
        assert resp.status_code == 422

    def test_422_when_missing_name(self, client: TestClient) -> None:
        resp = client.post("/organisations", json={"slug": "ok-slug"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /organisations/{org_id}
# ---------------------------------------------------------------------------

class TestPatchOrganisation:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1, name="Ancien")
        resp = client.patch("/organisations/1", json={"name": "Nouveau"})
        assert resp.status_code == 200
        assert resp.json()["id"] == 1

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.patch("/organisations/99", json={"name": "X"}).status_code == 404

    def test_response_contains_name(self, client: TestClient, mock_db: AsyncMock) -> None:
        org = _make_org(id=2, name="Ancien")
        mock_db.get.return_value = org
        resp = client.patch("/organisations/2", json={"name": "Nouveau"})
        assert "name" in resp.json()


# ---------------------------------------------------------------------------
# POST /organisations/{org_id}/archive
# ---------------------------------------------------------------------------

class TestArchiveOrganisation:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1, deleted_at=None)
        resp = client.post("/organisations/1/archive")
        assert resp.status_code == 200
        assert resp.json()["archived"] is True

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.post("/organisations/99/archive").status_code == 404

    def test_409_when_already_archived(self, client: TestClient, mock_db: AsyncMock) -> None:
        org = _make_org(id=1)
        org.deleted_at = "2026-01-01T00:00:00Z"
        mock_db.get.return_value = org
        assert client.post("/organisations/1/archive").status_code == 409


# ---------------------------------------------------------------------------
# POST /organisations/{org_id}/restore
# ---------------------------------------------------------------------------

class TestRestoreOrganisation:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        org = _make_org(id=1)
        org.deleted_at = "2026-01-01T00:00:00Z"
        mock_db.get.return_value = org
        resp = client.post("/organisations/1/restore")
        assert resp.status_code == 200
        assert resp.json()["archived"] is False

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.post("/organisations/99/restore").status_code == 404

    def test_409_when_not_archived(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1, deleted_at=None)
        assert client.post("/organisations/1/restore").status_code == 409
