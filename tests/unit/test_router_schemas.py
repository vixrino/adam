"""Tests unitaires adam_api/routers/schemas.py"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.schemas import router


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


def _make_schema(id: int = 1, name: str = "Schema", document_type: str = "FACTURE") -> MagicMock:
    row = MagicMock()
    row.id = id
    row.name = name
    row.document_type = document_type
    row.field_specs = []
    return row


def _make_field_spec(id: int = 1, field_key: str = "nom") -> MagicMock:
    fs = MagicMock()
    fs.id = id
    fs.field_key = field_key
    return fs


# ---------------------------------------------------------------------------
# GET /schemas
# ---------------------------------------------------------------------------

class TestListSchemas:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/schemas").status_code == 200

    def test_returns_empty_list(self, client: TestClient) -> None:
        assert client.get("/schemas").json() == []

    def test_returns_list(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_schema(id=1, name="S1"),
            _make_schema(id=2, name="S2"),
        ]
        data = client.get("/schemas").json()
        assert len(data) == 2
        assert data[0]["name"] == "S1"

    def test_response_contains_document_type(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_schema(document_type="CONTRAT"),
        ]
        data = client.get("/schemas").json()
        assert data[0]["document_type"] == "CONTRAT"

    def test_filter_by_project_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_schema(id=3)]
        data = client.get("/schemas?project_id=2").json()
        assert data[0]["id"] == 3


# ---------------------------------------------------------------------------
# GET /schemas/{schema_id}
# ---------------------------------------------------------------------------

class TestGetSchema:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_schema(id=1)
        assert client.get("/schemas/1").status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.get("/schemas/99").status_code == 404

    def test_contains_field_specs(self, client: TestClient, mock_db: AsyncMock) -> None:
        schema = _make_schema(id=1)
        schema.field_specs = [_make_field_spec(id=1, field_key="nom"), _make_field_spec(id=2, field_key="prenom")]
        mock_db.execute.return_value.scalar_one_or_none.return_value = schema
        data = client.get("/schemas/1").json()
        assert len(data["field_specs"]) == 2
        assert data["field_specs"][0]["field_key"] == "nom"

    def test_empty_field_specs(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_schema(id=1)
        data = client.get("/schemas/1").json()
        assert data["field_specs"] == []


# ---------------------------------------------------------------------------
# POST /schemas
# ---------------------------------------------------------------------------

class TestCreateSchema:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        resp = client.post("/schemas", json={"project_id": 1, "name": "Nouveau", "document_type": "FACTURE"})
        assert resp.status_code == 201

    def test_422_when_missing_name(self, client: TestClient) -> None:
        resp = client.post("/schemas", json={"project_id": 1, "document_type": "FACTURE"})
        assert resp.status_code == 422

    def test_422_when_missing_document_type(self, client: TestClient) -> None:
        resp = client.post("/schemas", json={"project_id": 1, "name": "S"})
        assert resp.status_code == 422

    def test_response_contains_id_and_name(self, client: TestClient, mock_db: AsyncMock) -> None:
        resp = client.post("/schemas", json={"project_id": 1, "name": "Test", "document_type": "CONTRAT"})
        assert {"id", "name"} <= resp.json().keys()
