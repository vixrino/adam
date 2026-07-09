"""Tests unitaires adam_api/routers/projects.py"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.projects import router

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


def _make_project(id: int = 1, name: str = "Projet", organisation_id: int = 1, status: str = "ACTIVE") -> MagicMock:
    row = MagicMock()
    row.id = id
    row.name = name
    row.organisation_id = organisation_id
    row.status = status
    row.updated_at = _NOW
    return row


def _make_up(user_id: int = 5, project_id: int = 1, role: str = "OPERATOR") -> MagicMock:
    up = MagicMock()
    up.user_id = user_id
    up.project_id = project_id
    up.role = role
    up.updated_at = _NOW
    return up


# ---------------------------------------------------------------------------
# GET /projects
# ---------------------------------------------------------------------------

class TestListProjects:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/projects").status_code == 200

    def test_returns_empty_list(self, client: TestClient) -> None:
        assert client.get("/projects").json() == []

    def test_returns_list(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_project(id=1, name="P1"), _make_project(id=2, name="P2"),
        ]
        data = client.get("/projects").json()
        assert len(data) == 2
        assert data[0]["name"] == "P1"

    def test_filter_by_organisation_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_project(organisation_id=3)]
        data = client.get("/projects?organisation_id=3").json()
        assert data[0]["organisation_id"] == 3


# ---------------------------------------------------------------------------
# GET /projects/{project_id}
# ---------------------------------------------------------------------------

class TestGetProject:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        assert client.get("/projects/1").status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.get("/projects/99").status_code == 404

    def test_response_contains_status_and_updated_at(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1, status="ARCHIVED")
        data = client.get("/projects/1").json()
        assert data["status"] == "ARCHIVED"
        assert "updated_at" in data


# ---------------------------------------------------------------------------
# POST /projects
# ---------------------------------------------------------------------------

class TestCreateProject:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        assert client.post("/projects", json={"organisation_id": 1, "name": "Nouveau"}).status_code == 201

    def test_422_when_missing_name(self, client: TestClient) -> None:
        assert client.post("/projects", json={"organisation_id": 1}).status_code == 422

    def test_422_when_missing_organisation_id(self, client: TestClient) -> None:
        assert client.post("/projects", json={"name": "P"}).status_code == 422


# ---------------------------------------------------------------------------
# POST /projects/{project_id}/users
# ---------------------------------------------------------------------------

class TestAddUserToProject:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        assert client.post("/projects/1/users", json={"user_id": 5}).status_code == 201

    def test_404_when_project_not_found(self, client: TestClient) -> None:
        assert client.post("/projects/99/users", json={"user_id": 1}).status_code == 404

    def test_response_contains_role(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        data = client.post("/projects/1/users", json={"user_id": 5, "role": "SUPERVISOR"}).json()
        assert data["role"] == "SUPERVISOR"
        assert data["project_id"] == 1
        assert data["user_id"] == 5


# ---------------------------------------------------------------------------
# PATCH /projects/{project_id}
# ---------------------------------------------------------------------------

class TestPatchProject:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        assert client.patch("/projects/1", json={"name": "Nouveau"}).status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.patch("/projects/99", json={"name": "X"}).status_code == 404

    def test_422_on_invalid_status(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        assert client.patch("/projects/1", json={"status": "INVALID"}).status_code == 422

    def test_valid_status_accepted(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        assert client.patch("/projects/1", json={"status": "ARCHIVED"}).status_code == 200

    def test_response_contains_updated_at(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        data = client.patch("/projects/1", json={"name": "X"}).json()
        assert "updated_at" in data


# ---------------------------------------------------------------------------
# PATCH /projects/{project_id}/users/{user_id}
# ---------------------------------------------------------------------------

class TestUpdateUserRole:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_up()
        assert client.patch("/projects/1/users/5", json={"role": "SUPERVISOR"}).status_code == 200

    def test_404_when_user_not_in_project(self, client: TestClient) -> None:
        assert client.patch("/projects/1/users/99", json={"role": "OPERATOR"}).status_code == 404

    def test_422_on_invalid_role(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_up()
        assert client.patch("/projects/1/users/5", json={"role": "INVALID"}).status_code == 422

    def test_response_contains_role_and_updated_at(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_up(role="OPERATOR")
        data = client.patch("/projects/1/users/5", json={"role": "SUPERVISOR"}).json()
        assert "role" in data
        assert "updated_at" in data
        assert data["user_id"] == 5
        assert data["project_id"] == 1


# ---------------------------------------------------------------------------
# DELETE /projects/{project_id}/users/{user_id}
# ---------------------------------------------------------------------------

class TestRemoveUserFromProject:
    def test_returns_204(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_up()
        assert client.delete("/projects/1/users/5").status_code == 204

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.delete("/projects/1/users/99").status_code == 404
