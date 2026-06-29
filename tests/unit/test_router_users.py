"""Tests unitaires adam_api/routers/users.py"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.users import router


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
    matricule: str = "M001",
    status: str = "ACTIVE",
) -> MagicMock:
    row = MagicMock()
    row.id = id
    row.email = email
    row.matricule = matricule
    row.status = status
    return row


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

    def test_filter_by_organisation_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_user(id=5)]
        data = client.get("/users?organisation_id=2").json()
        assert data[0]["id"] == 5

    def test_response_contains_matricule(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_user(matricule="X999"),
        ]
        data = client.get("/users").json()
        assert data[0]["matricule"] == "X999"


# ---------------------------------------------------------------------------
# GET /users/{user_id}
# ---------------------------------------------------------------------------

class TestGetUser:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_user(id=1)
        assert client.get("/users/1").status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.get("/users/99").status_code == 404

    def test_response_contains_email_and_status(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_user(id=1, email="z@x.com", status="SUSPENDED")
        data = client.get("/users/1").json()
        assert data["email"] == "z@x.com"
        assert data["status"] == "SUSPENDED"

    def test_response_does_not_contain_matricule(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_user(id=1)
        data = client.get("/users/1").json()
        assert "matricule" not in data


# ---------------------------------------------------------------------------
# POST /users
# ---------------------------------------------------------------------------

class TestCreateUser:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        resp = client.post("/users", json={
            "organisation_id": 1,
            "email": "new@example.com",
            "full_name": "Jean Dupont",
            "matricule": "J001",
        })
        assert resp.status_code == 201

    def test_422_on_invalid_email(self, client: TestClient) -> None:
        resp = client.post("/users", json={
            "organisation_id": 1,
            "email": "not-an-email",
            "full_name": "Jean",
            "matricule": "J001",
        })
        assert resp.status_code == 422

    def test_422_when_missing_fields(self, client: TestClient) -> None:
        resp = client.post("/users", json={"email": "a@b.com"})
        assert resp.status_code == 422

    def test_response_contains_id_and_email(self, client: TestClient, mock_db: AsyncMock) -> None:
        resp = client.post("/users", json={
            "organisation_id": 1,
            "email": "new@example.com",
            "full_name": "Jean",
            "matricule": "J001",
        })
        assert {"id", "email"} <= resp.json().keys()


# ---------------------------------------------------------------------------
# PATCH /users/{user_id}
# ---------------------------------------------------------------------------

class TestPatchUser:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_user(id=1)
        assert client.patch("/users/1", json={"status": "INACTIVE"}).status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.patch("/users/99", json={"status": "INACTIVE"}).status_code == 404

    def test_response_contains_status(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_user(id=1, status="ACTIVE")
        data = client.patch("/users/1", json={"status": "SUSPENDED"}).json()
        assert "status" in data
        assert data["id"] == 1
