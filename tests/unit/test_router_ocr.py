"""Tests unitaires adam_api/routers/ocr.py"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.ocr import router

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
    db.add_all = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    result.scalar_one.return_value = 0
    db.execute.return_value = result
    db.get.return_value = None
    return db


@pytest.fixture
def client(app: FastAPI, mock_db: AsyncMock) -> TestClient:
    from adam_api.dependencies.db import get_db
    app.dependency_overrides[get_db] = lambda: mock_db
    return TestClient(app, raise_server_exceptions=False)


def _make_ocr(
    id: int = 1,
    document_id: int = 1,
    dataset_id: int = 1,
    storage_mode: str = "JSONB",
    raw_json: dict | None = None,
) -> MagicMock:
    row = MagicMock()
    row.id = id
    row.document_id = document_id
    row.dataset_id = dataset_id
    row.storage_mode = storage_mode
    row.processed_at = _NOW
    row.raw_json = raw_json or {}
    return row


def _make_doc(id: int = 1, status: str = "RECEIVED") -> MagicMock:
    doc = MagicMock()
    doc.id = id
    doc.status = status
    return doc


# ---------------------------------------------------------------------------
# GET /ocr-results
# ---------------------------------------------------------------------------

class TestListOcrResults:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/ocr-results").status_code == 200

    def test_returns_empty_list(self, client: TestClient) -> None:
        assert client.get("/ocr-results").json() == []

    def test_returns_list(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_ocr(id=1), _make_ocr(id=2),
        ]
        data = client.get("/ocr-results").json()
        assert len(data) == 2
        assert data[0]["id"] == 1

    def test_response_contains_storage_mode_and_processed_at(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_ocr()]
        data = client.get("/ocr-results").json()
        assert "storage_mode" in data[0]
        assert "processed_at" in data[0]

    def test_filter_by_document_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_ocr(document_id=5)]
        data = client.get("/ocr-results?document_id=5").json()
        assert data[0]["document_id"] == 5

    def test_filter_by_dataset_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_ocr(dataset_id=3)]
        data = client.get("/ocr-results?dataset_id=3").json()
        assert data[0]["dataset_id"] == 3


# ---------------------------------------------------------------------------
# GET /ocr-results/{ocr_result_id}
# ---------------------------------------------------------------------------

class TestGetOcrResult:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_ocr(id=1)
        assert client.get("/ocr-results/1").status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.get("/ocr-results/99").status_code == 404

    def test_response_contains_all_fields(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_ocr(id=1, storage_mode="JSONB", raw_json={"key": "val"})
        data = client.get("/ocr-results/1").json()
        assert {"id", "document_id", "dataset_id", "storage_mode", "processed_at", "raw_json"} <= data.keys()

    def test_raw_json_returned_for_jsonb_mode(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_ocr(storage_mode="JSONB", raw_json={"pages": []})
        data = client.get("/ocr-results/1").json()
        assert data["raw_json"] == {"pages": []}

    def test_raw_json_null_for_file_mode(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_ocr(storage_mode="file", raw_json={"pages": []})
        data = client.get("/ocr-results/1").json()
        assert data["raw_json"] is None


# ---------------------------------------------------------------------------
# POST /ocr-results
# ---------------------------------------------------------------------------

class TestPostOcrResult:
    def test_404_when_document_not_found(self, client: TestClient) -> None:
        resp = client.post("/ocr-results", json={
            "document_id": 99, "dataset_id": 1, "raw_json": {}
        })
        assert resp.status_code == 404

    def test_404_when_dataset_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.side_effect = [_make_doc(), None]
        resp = client.post("/ocr-results", json={
            "document_id": 1, "dataset_id": 99, "raw_json": {}
        })
        assert resp.status_code == 404

    def test_returns_201_with_correct_schema(self, client: TestClient, mock_db: AsyncMock) -> None:
        doc = _make_doc(id=1)
        dataset = MagicMock()
        dataset.schema_id = 1
        mock_db.get.side_effect = [doc, dataset]

        no_specs = MagicMock()
        no_specs.scalars.return_value.all.return_value = []
        no_existing = MagicMock()
        no_existing.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [no_specs, no_existing]

        with patch("adam_api.routers.ocr.SmartdocDocument") as mock_form:
            mock_form.model_validate.return_value.iter_kv_pairs.return_value = []
            resp = client.post("/ocr-results", json={
                "document_id": 1, "dataset_id": 1, "raw_json": {"pages": []}
            })

        assert resp.status_code == 201
        data = resp.json()
        assert "ocr_result_id" in data
        assert "document_fields_created" in data
        assert "document_fields_skipped" in data
        assert "document_status" in data

    def test_skips_existing_field_specs(self, client: TestClient, mock_db: AsyncMock) -> None:
        doc = _make_doc(id=1)
        dataset = MagicMock()
        dataset.schema_id = 1
        mock_db.get.side_effect = [doc, dataset]

        fs = MagicMock()
        fs.id = 10
        fs.section_id = "s1"
        fs.field_key = "nom"

        specs_result = MagicMock()
        specs_result.scalars.return_value.all.return_value = [fs]
        existing_result = MagicMock()
        existing_result.scalars.return_value.all.return_value = [10]  # already exists
        mock_db.execute.side_effect = [specs_result, existing_result]

        with patch("adam_api.routers.ocr.SmartdocDocument") as mock_form:
            mock_form.model_validate.return_value.iter_kv_pairs.return_value = []
            resp = client.post("/ocr-results", json={
                "document_id": 1, "dataset_id": 1, "raw_json": {}
            })

        data = resp.json()
        assert data["document_fields_created"] == 0
        assert data["document_fields_skipped"] == 1
