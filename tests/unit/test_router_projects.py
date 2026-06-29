"""Tests unitaires adam_api/routers/projects.py"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.projects import router


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
    return row


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
            _make_project(id=1, name="P1"),
            _make_project(id=2, name="P2"),
        ]
        data = client.get("/projects").json()
        assert len(data) == 2
        assert data[0]["name"] == "P1"

    def test_filter_by_organisation_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_project(id=1, organisation_id=3),
        ]
        data = client.get("/projects?organisation_id=3").json()
        assert data[0]["organisation_id"] == 3

    def test_response_contains_expected_fields(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_project()]
        data = client.get("/projects").json()
        assert {"id", "name", "organisation_id"} <= data[0].keys()


# ---------------------------------------------------------------------------
# GET /projects/{project_id}
# ---------------------------------------------------------------------------

class TestGetProject:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        assert client.get("/projects/1").status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.get("/projects/99").status_code == 404

    def test_response_contains_status(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1, status="ARCHIVED")
        data = client.get("/projects/1").json()
        assert data["status"] == "ARCHIVED"


# ---------------------------------------------------------------------------
# POST /projects
# ---------------------------------------------------------------------------

class TestCreateProject:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        resp = client.post("/projects", json={"organisation_id": 1, "name": "Nouveau"})
        assert resp.status_code == 201

    def test_422_when_missing_name(self, client: TestClient) -> None:
        resp = client.post("/projects", json={"organisation_id": 1})
        assert resp.status_code == 422

    def test_422_when_missing_organisation_id(self, client: TestClient) -> None:
        resp = client.post("/projects", json={"name": "P"})
        assert resp.status_code == 422

    def test_response_contains_id_and_name(self, client: TestClient, mock_db: AsyncMock) -> None:
        resp = client.post("/projects", json={"organisation_id": 1, "name": "Test"})
        assert {"id", "name"} <= resp.json().keys()


# ---------------------------------------------------------------------------
# POST /projects/{project_id}/users
# ---------------------------------------------------------------------------

class TestAddUserToProject:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        resp = client.post("/projects/1/users", json={"user_id": 5})
        assert resp.status_code == 201

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


# ---------------------------------------------------------------------------
# DELETE /projects/{project_id}/users/{user_id}
# ---------------------------------------------------------------------------

class TestRemoveUserFromProject:
    def test_returns_204(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = MagicMock()
        assert client.delete("/projects/1/users/5").status_code == 204

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.delete("/projects/1/users/99").status_code == 404
