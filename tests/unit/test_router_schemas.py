"""Tests unitaires adam_api/routers/schemas.py"""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.schemas import router

_NOW = datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc)

_VALID_SPEC = {
    "page": 1,
    "section_id": "identite",
    "section_label": "Identite",
    "field_key": "identite.nom",
    "display_label": "Nom",
    "value_type": "text",
}


@pytest.fixture
def app() -> FastAPI:
    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    return fastapi_app


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock(side_effect=lambda obj: setattr(obj, "id", 1))
    db.add_all = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    result.scalar_one.return_value = None
    db.execute.return_value = result
    db.get.return_value = None
    return db


@pytest.fixture
def client(app: FastAPI, mock_db: AsyncMock) -> TestClient:
    from adam_api.dependencies.db import get_db
    app.dependency_overrides[get_db] = lambda: mock_db
    return TestClient(app, raise_server_exceptions=False)


def _make_schema(
    id: int = 1,
    name: str = "Schema Test",
    document_type: str = "IDENTITE",
    project_id: int = 1,
    version: int = 1,
    field_specs: list | None = None,
) -> MagicMock:
    row = MagicMock()
    row.id = id
    row.name = name
    row.document_type = document_type
    row.project_id = project_id
    row.version = version
    row.created_at = _NOW
    row.updated_at = _NOW
    row.field_specs = field_specs or []
    return row


def _make_field_spec(
    id: int = 10,
    schema_id: int = 1,
    field_key: str = "identite.nom",
    section_id: str = "identite",
    section_label: str = "Identite",
    display_label: str = "Nom",
    page: int = 1,
    value_type: str = "text",
    required: bool = False,
    display_order: int = 0,
    group_id: Any = None,
    polygon: Any = None,
) -> MagicMock:
    fs = MagicMock()
    fs.id = id
    fs.schema_id = schema_id
    fs.field_key = field_key
    fs.section_id = section_id
    fs.section_label = section_label
    fs.display_label = display_label
    fs.page = page
    fs.value_type = value_type
    fs.required = required
    fs.display_order = display_order
    fs.group_id = group_id
    fs.polygon = polygon
    fs.updated_at = _NOW
    return fs


def _unlocked_db(mock_db: AsyncMock) -> AsyncMock:
    """Configure le mock pour simuler un schema non verrouille et sans DocumentFields."""
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    mock_db.execute.return_value.scalar_one.return_value = 0
    return mock_db


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
            _make_schema(id=1, name="S1"), _make_schema(id=2, name="S2"),
        ]
        data = client.get("/schemas").json()
        assert len(data) == 2
        assert data[0]["name"] == "S1"

    def test_response_contains_version_and_project_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_schema(version=3, project_id=5)]
        data = client.get("/schemas").json()
        assert data[0]["version"] == 3
        assert data[0]["project_id"] == 5
        assert "created_at" in data[0]

    def test_filter_by_project_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_schema(project_id=5)]
        data = client.get("/schemas?project_id=5").json()
        assert len(data) == 1


# ---------------------------------------------------------------------------
# GET /schemas/field-specs/{field_spec_id}
# ---------------------------------------------------------------------------

class TestGetFieldSpec:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_field_spec(id=10)
        assert client.get("/schemas/field-specs/10").status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.get("/schemas/field-specs/99").status_code == 404

    def test_response_contains_schema_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_field_spec(id=10, schema_id=3)
        data = client.get("/schemas/field-specs/10").json()
        assert data["schema_id"] == 3
        expected = {"id", "schema_id", "page", "section_id", "section_label", "field_key", "display_label", "value_type", "required"}
        assert expected <= data.keys()


# ---------------------------------------------------------------------------
# GET /schemas/{schema_id}
# ---------------------------------------------------------------------------

class TestGetSchema:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_schema(id=1)
        assert client.get("/schemas/1").status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.get("/schemas/99").status_code == 404

    def test_response_contains_all_fields(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_schema(id=1)
        data = client.get("/schemas/1").json()
        expected = {"id", "name", "document_type", "version", "project_id", "created_at", "updated_at", "field_specs"}
        assert expected <= data.keys()
        assert data["field_specs"] == []

    def test_response_contains_field_specs(self, client: TestClient, mock_db: AsyncMock) -> None:
        fs = _make_field_spec(id=10, field_key="identite.nom")
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_schema(id=1, field_specs=[fs])
        data = client.get("/schemas/1").json()
        assert len(data["field_specs"]) == 1
        spec = data["field_specs"][0]
        assert spec["id"] == 10
        assert spec["field_key"] == "identite.nom"


# ---------------------------------------------------------------------------
# POST /schemas
# ---------------------------------------------------------------------------

class TestCreateSchema:
    def test_returns_201(self, client: TestClient) -> None:
        resp = client.post("/schemas", json={
            "project_id": 1, "name": "Nouveau Schema", "document_type": "IDENTITE"
        })
        assert resp.status_code == 201

    def test_422_when_missing_document_type(self, client: TestClient) -> None:
        assert client.post("/schemas", json={"project_id": 1, "name": "X"}).status_code == 422

    def test_422_when_missing_name(self, client: TestClient) -> None:
        assert client.post("/schemas", json={"project_id": 1, "document_type": "T"}).status_code == 422

    def test_response_contains_version_and_field_specs_created(self, client: TestClient) -> None:
        data = client.post("/schemas", json={
            "project_id": 1, "name": "Schema", "document_type": "IDENTITE"
        }).json()
        assert "version" in data
        assert "field_specs_created" in data
        assert data["field_specs_created"] == 0

    def test_creates_field_specs_in_same_request(self, client: TestClient) -> None:
        data = client.post("/schemas", json={
            "project_id": 1, "name": "Schema", "document_type": "IDENTITE",
            "field_specs": [_VALID_SPEC],
        }).json()
        assert data["field_specs_created"] == 1

    def test_422_on_invalid_field_key_in_field_specs(self, client: TestClient) -> None:
        resp = client.post("/schemas", json={
            "project_id": 1, "name": "Schema", "document_type": "IDENTITE",
            "field_specs": [{**_VALID_SPEC, "field_key": "invalid-key"}],
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /schemas/{schema_id}/field-specs
# ---------------------------------------------------------------------------

class TestAddFieldSpec:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        _unlocked_db(mock_db)
        mock_db.get.return_value = _make_schema(id=1)
        resp = client.post("/schemas/1/field-specs", json=_VALID_SPEC)
        assert resp.status_code == 201

    def test_404_when_schema_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        _unlocked_db(mock_db)
        resp = client.post("/schemas/99/field-specs", json=_VALID_SPEC)
        assert resp.status_code == 404

    def test_423_when_schema_locked(self, client: TestClient, mock_db: AsyncMock) -> None:
        locked_dataset = MagicMock()
        locked_dataset.name = "Dataset Actif"
        locked_dataset.status = "ACTIVE"
        mock_db.execute.return_value.scalar_one_or_none.return_value = locked_dataset
        resp = client.post("/schemas/1/field-specs", json=_VALID_SPEC)
        assert resp.status_code == 423

    def test_422_on_invalid_field_key_format(self, client: TestClient, mock_db: AsyncMock) -> None:
        _unlocked_db(mock_db)
        mock_db.get.return_value = _make_schema(id=1)
        bad_spec = {**_VALID_SPEC, "field_key": "invalid-key"}
        assert client.post("/schemas/1/field-specs", json=bad_spec).status_code == 422

    def test_response_contains_id_field_key_schema_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        _unlocked_db(mock_db)
        mock_db.get.return_value = _make_schema(id=1)
        data = client.post("/schemas/1/field-specs", json=_VALID_SPEC).json()
        assert {"id", "field_key", "schema_id"} <= data.keys()

    def test_polygon_must_have_8_points(self, client: TestClient, mock_db: AsyncMock) -> None:
        _unlocked_db(mock_db)
        mock_db.get.return_value = _make_schema(id=1)
        bad_spec = {**_VALID_SPEC, "polygon": [1.0, 2.0, 3.0]}
        assert client.post("/schemas/1/field-specs", json=bad_spec).status_code == 422

    def test_polygon_with_8_points_accepted(self, client: TestClient, mock_db: AsyncMock) -> None:
        _unlocked_db(mock_db)
        mock_db.get.return_value = _make_schema(id=1)
        spec = {**_VALID_SPEC, "polygon": [0.0, 0.0, 1.0, 0.0, 1.0, 1.0, 0.0, 1.0]}
        assert client.post("/schemas/1/field-specs", json=spec).status_code == 201


# ---------------------------------------------------------------------------
# POST /schemas/{schema_id}/duplicate
# ---------------------------------------------------------------------------

class TestDuplicateSchema:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        source = _make_schema(id=1, version=1, field_specs=[])
        mock_db.execute.return_value.scalar_one_or_none.return_value = source
        mock_db.execute.return_value.scalar_one.return_value = 1
        resp = client.post("/schemas/1/duplicate")
        assert resp.status_code == 201

    def test_404_when_source_not_found(self, client: TestClient) -> None:
        assert client.post("/schemas/99/duplicate").status_code == 404

    def test_response_contains_incremented_version(self, client: TestClient, mock_db: AsyncMock) -> None:
        source = _make_schema(id=1, version=2, field_specs=[])
        # first execute call (get_schema with options) returns source
        results = [MagicMock(), MagicMock()]
        results[0].scalar_one_or_none.return_value = source
        results[1].scalar_one.return_value = 2  # latest version
        call_count = 0

        async def _exec(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            r = results[min(call_count, len(results) - 1)]
            call_count += 1
            return r

        mock_db.execute.side_effect = _exec
        data = client.post("/schemas/1/duplicate").json()
        assert "version" in data
        assert "field_specs_created" in data

    def test_copies_field_specs(self, client: TestClient, mock_db: AsyncMock) -> None:
        fs = _make_field_spec(id=10, schema_id=1)
        source = _make_schema(id=1, version=1, field_specs=[fs])
        results = [MagicMock(), MagicMock()]
        results[0].scalar_one_or_none.return_value = source
        results[1].scalar_one.return_value = 1
        call_count = 0

        async def _exec(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            r = results[min(call_count, len(results) - 1)]
            call_count += 1
            return r

        mock_db.execute.side_effect = _exec
        data = client.post("/schemas/1/duplicate").json()
        assert data.get("field_specs_created", 0) == 1


# ---------------------------------------------------------------------------
# PATCH /schemas/{schema_id}/field-specs/{spec_id}
# ---------------------------------------------------------------------------

class TestPatchFieldSpec:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        _unlocked_db(mock_db)
        fs = _make_field_spec(id=10, schema_id=1)
        mock_db.get.return_value = fs
        assert client.patch("/schemas/1/field-specs/10", json={"display_label": "Nouveau Label"}).status_code == 200

    def test_404_when_spec_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        _unlocked_db(mock_db)
        assert client.patch("/schemas/1/field-specs/99", json={"display_label": "X"}).status_code == 404

    def test_404_when_spec_belongs_to_other_schema(self, client: TestClient, mock_db: AsyncMock) -> None:
        _unlocked_db(mock_db)
        fs = _make_field_spec(id=10, schema_id=999)
        mock_db.get.return_value = fs
        assert client.patch("/schemas/1/field-specs/10", json={"display_label": "X"}).status_code == 404

    def test_423_when_schema_locked(self, client: TestClient, mock_db: AsyncMock) -> None:
        locked = MagicMock()
        locked.name = "DS"
        locked.status = "ACTIVE"
        mock_db.execute.return_value.scalar_one_or_none.return_value = locked
        assert client.patch("/schemas/1/field-specs/10", json={"required": True}).status_code == 423

    def test_section_label_can_be_patched(self, client: TestClient, mock_db: AsyncMock) -> None:
        _unlocked_db(mock_db)
        fs = _make_field_spec(id=10, schema_id=1)
        mock_db.get.return_value = fs
        assert client.patch("/schemas/1/field-specs/10", json={"section_label": "Nouveau"}).status_code == 200


# ---------------------------------------------------------------------------
# DELETE /schemas/{schema_id}/field-specs/{spec_id}
# ---------------------------------------------------------------------------

class TestDeleteFieldSpec:
    def test_returns_204(self, client: TestClient, mock_db: AsyncMock) -> None:
        _unlocked_db(mock_db)
        fs = _make_field_spec(id=10, schema_id=1)
        mock_db.get.return_value = fs
        assert client.delete("/schemas/1/field-specs/10").status_code == 204

    def test_404_when_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        _unlocked_db(mock_db)
        assert client.delete("/schemas/1/field-specs/99").status_code == 404

    def test_404_when_spec_belongs_to_other_schema(self, client: TestClient, mock_db: AsyncMock) -> None:
        _unlocked_db(mock_db)
        fs = _make_field_spec(id=10, schema_id=999)
        mock_db.get.return_value = fs
        assert client.delete("/schemas/1/field-specs/10").status_code == 404

    def test_423_when_schema_locked(self, client: TestClient, mock_db: AsyncMock) -> None:
        locked = MagicMock()
        locked.name = "DS"
        locked.status = "ARCHIVED"
        mock_db.execute.return_value.scalar_one_or_none.return_value = locked
        assert client.delete("/schemas/1/field-specs/10").status_code == 423

    def test_409_when_referenced_by_document_field(self, client: TestClient, mock_db: AsyncMock) -> None:
        fs = _make_field_spec(id=10, schema_id=1)
        mock_db.get.return_value = fs
        # premier execute : lock check (pas verrouille)
        # deuxieme execute : compte les DocumentFields → 3 references
        not_locked = MagicMock()
        not_locked.scalar_one_or_none.return_value = None
        doc_field_count = MagicMock()
        doc_field_count.scalar_one.return_value = 3
        results = [not_locked, doc_field_count]
        call_count = 0

        async def _exec(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            r = results[min(call_count, len(results) - 1)]
            call_count += 1
            return r

        mock_db.execute.side_effect = _exec
        assert client.delete("/schemas/1/field-specs/10").status_code == 409
