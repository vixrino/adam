"""Tests unitaires adam_api/routers/users.py"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.users import router

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


def _make_user(
    id: int = 1,
    email: str = "user@example.com",
    full_name: str = "Jean Dupont",
    matricule: str = "M001",
    status: str = "ACTIVE",
    organisation_id: int = 1,
    deleted_at: datetime | None = None,
    user_projects: list | None = None,
) -> MagicMock:
    u = MagicMock()
    u.id = id
    u.email = email
    u.full_name = full_name
    u.matricule = matricule
    u.status = status
    u.organisation_id = organisation_id
    u.created_at = _NOW
    u.updated_at = _NOW
    u.last_login_at = None
    u.deleted_at = deleted_at
    u.user_projects = user_projects or []
    return u


def _make_user_project(project_id: int = 10, role: str = "OPERATOR") -> MagicMock:
    up = MagicMock()
    up.project_id = project_id
    up.role = role
    up.created_at = _NOW
    return up


# ---------------------------------------------------------------------------
# GET /users
# ---------------------------------------------------------------------------

class TestListUsers:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/users").status_code == 200

    def test_returns_empty_list(self, client: TestClient) -> None:
        assert client.get("/users").json() == []

    def test_returns_list(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_user(id=1, email="a@x.com"),
            _make_user(id=2, email="b@x.com"),
        ]
        data = client.get("/users").json()
        assert len(data) == 2
        assert data[0]["email"] == "a@x.com"

    def test_response_contains_all_fields(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_user()]
        data = client.get("/users").json()
        expected = {"id", "email", "full_name", "matricule", "status", "organisation_id", "created_at", "updated_at", "deleted_at"}
        assert expected <= data[0].keys()

    def test_filter_by_organisation_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_user(organisation_id=3)]
        data = client.get("/users?organisation_id=3").json()
        assert data[0]["organisation_id"] == 3

    def test_filter_by_status(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_user(status="INACTIVE")]
        data = client.get("/users?status=INACTIVE").json()
        assert data[0]["status"] == "INACTIVE"

    def test_include_deleted_false_by_default(self, client: TestClient) -> None:
        assert client.get("/users").status_code == 200


# ---------------------------------------------------------------------------
# GET /users/{user_id}
# ---------------------------------------------------------------------------

class TestGetUser:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_user(id=1)
        assert client.get("/users/1").status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.get("/users/99").status_code == 404

    def test_response_contains_all_fields(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_user(id=1)
        data = client.get("/users/1").json()
        expected = {"id", "email", "full_name", "matricule", "status", "organisation_id",
                    "created_at", "last_login_at", "updated_at", "deleted_at", "projects"}
        assert expected <= data.keys()

    def test_response_contains_projects(self, client: TestClient, mock_db: AsyncMock) -> None:
        up = _make_user_project(project_id=5, role="SUPERVISOR")
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_user(user_projects=[up])
        data = client.get("/users/1").json()
        assert len(data["projects"]) == 1
        assert data["projects"][0]["project_id"] == 5
        assert data["projects"][0]["role"] == "SUPERVISOR"

    def test_empty_projects(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_user()
        data = client.get("/users/1").json()
        assert data["projects"] == []


# ---------------------------------------------------------------------------
# POST /users
# ---------------------------------------------------------------------------

class TestCreateUser:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        resp = client.post("/users", json={
            "organisation_id": 1, "email": "new@x.com", "full_name": "Jean", "matricule": "J001"
        })
        assert resp.status_code == 201

    def test_response_contains_expected_fields(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        data = client.post("/users", json={
            "organisation_id": 1, "email": "new@x.com", "full_name": "Jean", "matricule": "J001"
        }).json()
        assert {"id", "email", "full_name", "matricule", "status"} <= data.keys()

    def test_409_on_duplicate_email(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_user()
        resp = client.post("/users", json={
            "organisation_id": 1, "email": "dup@x.com", "full_name": "J", "matricule": "X"
        })
        assert resp.status_code == 409

    def test_422_when_missing_fields(self, client: TestClient) -> None:
        assert client.post("/users", json={"email": "a@b.com"}).status_code == 422


# ---------------------------------------------------------------------------
# PATCH /users/{user_id}
# ---------------------------------------------------------------------------

class TestPatchUser:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_user(id=1)
        assert client.patch("/users/1", json={"status": "INACTIVE"}).status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.patch("/users/99", json={"status": "INACTIVE"}).status_code == 404

    def test_422_on_invalid_status(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_user(id=1)
        assert client.patch("/users/1", json={"status": "INVALID"}).status_code == 422

    def test_response_contains_full_user(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_user(id=1)
        data = client.patch("/users/1", json={"full_name": "Nouveau Nom"}).json()
        assert {"id", "email", "full_name", "matricule", "status", "organisation_id"} <= data.keys()


# ---------------------------------------------------------------------------
# POST /users/{user_id}/archive
# ---------------------------------------------------------------------------

class TestArchiveUser:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_user(id=1, deleted_at=None)
        assert client.post("/users/1/archive").status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.post("/users/99/archive").status_code == 404

    def test_409_when_already_archived(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_user(id=1, deleted_at=_NOW)
        assert client.post("/users/1/archive").status_code == 409


# ---------------------------------------------------------------------------
# POST /users/{user_id}/restore
# ---------------------------------------------------------------------------

class TestRestoreUser:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_user(id=1, deleted_at=_NOW)
        assert client.post("/users/1/restore").status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.post("/users/99/restore").status_code == 404

    def test_409_when_not_archived(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_user(id=1, deleted_at=None)
        assert client.post("/users/1/restore").status_code == 409
