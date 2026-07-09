"""Tests unitaires adam_api/routers/organisations.py"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.organisations import router

_NOW = datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def app() -> FastAPI:
    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    return fastapi_app


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock(side_effect=lambda obj: setattr(obj, "id", 1))
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result
    db.get.return_value = None
    return db


@pytest.fixture
def client(app: FastAPI, mock_db: AsyncMock) -> TestClient:
    from adam_api.dependencies.db import get_db
    app.dependency_overrides[get_db] = lambda: mock_db
    return TestClient(app, raise_server_exceptions=False)


def _make_org(
    id: int = 1,
    name: str = "Org",
    slug: str = "org",
    deleted_at: datetime | None = None,
) -> MagicMock:
    row = MagicMock()
    row.id = id
    row.name = name
    row.slug = slug
    row.created_at = _NOW
    row.updated_at = _NOW
    row.deleted_at = deleted_at
    return row


def _make_user(
    id: int = 1,
    email: str = "u@example.com",
    full_name: str = "Jean Dupont",
    matricule: str = "M001",
    status: str = "ACTIVE",
    user_projects: list | None = None,
) -> MagicMock:
    row = MagicMock()
    row.id = id
    row.email = email
    row.full_name = full_name
    row.matricule = matricule
    row.status = status
    row.user_projects = user_projects or []
    row.deleted_at = None
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

    def test_response_contains_timestamps(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_org()]
        data = client.get("/organisations").json()
        assert {"id", "name", "slug", "created_at", "updated_at", "deleted_at"} <= data[0].keys()

    def test_filter_by_organisation_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_org(id=5)]
        data = client.get("/organisations?organisation_id=5").json()
        assert data[0]["id"] == 5

    def test_include_deleted_false_by_default(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        resp = client.get("/organisations")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /organisations/{organisation_id}/users
# ---------------------------------------------------------------------------

class TestListOrganisationUsers:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1)
        assert client.get("/organisations/1/users").status_code == 200

    def test_404_when_org_not_found(self, client: TestClient) -> None:
        assert client.get("/organisations/99/users").status_code == 404

    def test_404_when_org_archived(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1, deleted_at=_NOW)
        assert client.get("/organisations/1/users").status_code == 404

    def test_returns_users_with_projects(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1)
        up = MagicMock()
        up.project_id = 10
        up.role = "OPERATOR"
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_user(id=1, user_projects=[up]),
        ]
        data = client.get("/organisations/1/users").json()
        assert data[0]["email"] == "u@example.com"
        assert data[0]["full_name"] == "Jean Dupont"
        assert data[0]["projects"][0]["project_id"] == 10
        assert data[0]["projects"][0]["role"] == "OPERATOR"

    def test_user_without_projects(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1)
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_user()]
        data = client.get("/organisations/1/users").json()
        assert data[0]["projects"] == []


# ---------------------------------------------------------------------------
# POST /organisations
# ---------------------------------------------------------------------------

class TestCreateOrganisation:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        resp = client.post("/organisations", json={"name": "Nouvel Org", "slug": "nouvel-org"})
        assert resp.status_code == 201

    def test_response_contains_timestamps(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        data = client.post("/organisations", json={"name": "Org", "slug": "org"}).json()
        assert {"id", "name", "slug", "created_at", "updated_at", "deleted_at"} <= data.keys()

    def test_409_on_duplicate_slug(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_org()
        resp = client.post("/organisations", json={"name": "Org", "slug": "existing"})
        assert resp.status_code == 409

    def test_422_on_invalid_slug(self, client: TestClient) -> None:
        assert client.post("/organisations", json={"name": "Org", "slug": "INVALID SLUG"}).status_code == 422

    def test_422_when_missing_name(self, client: TestClient) -> None:
        assert client.post("/organisations", json={"slug": "ok-slug"}).status_code == 422


# ---------------------------------------------------------------------------
# PATCH /organisations/{organisation_id}
# ---------------------------------------------------------------------------

class TestPatchOrganisation:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1)
        assert client.patch("/organisations/1", json={"name": "Nouveau"}).status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.patch("/organisations/99", json={"name": "X"}).status_code == 404

    def test_409_when_archived(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1, deleted_at=_NOW)
        assert client.patch("/organisations/1", json={"name": "X"}).status_code == 409

    def test_response_contains_full_org(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1, name="Ancien", slug="ancien")
        data = client.patch("/organisations/1", json={"name": "Nouveau"}).json()
        assert {"id", "name", "slug", "created_at", "updated_at", "deleted_at"} <= data.keys()


# ---------------------------------------------------------------------------
# POST /organisations/{organisation_id}/archive
# ---------------------------------------------------------------------------

class TestArchiveOrganisation:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1, deleted_at=None)
        assert client.post("/organisations/1/archive").status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.post("/organisations/99/archive").status_code == 404

    def test_409_when_already_archived(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1, deleted_at=_NOW)
        assert client.post("/organisations/1/archive").status_code == 409

    def test_response_contains_full_org(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1, deleted_at=None)
        data = client.post("/organisations/1/archive").json()
        assert {"id", "name", "slug", "created_at", "updated_at"} <= data.keys()


# ---------------------------------------------------------------------------
# POST /organisations/{organisation_id}/restore
# ---------------------------------------------------------------------------

class TestRestoreOrganisation:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1, deleted_at=_NOW)
        assert client.post("/organisations/1/restore").status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.post("/organisations/99/restore").status_code == 404

    def test_409_when_not_archived(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1, deleted_at=None)
        assert client.post("/organisations/1/restore").status_code == 409

    def test_response_contains_full_org(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_org(id=1, deleted_at=_NOW)
        data = client.post("/organisations/1/restore").json()
        assert {"id", "name", "slug"} <= data.keys()
