"""Tests unitaires adam_api/routers/ocr.py"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.ocr import router


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


def _make_ocr(id: int = 1, document_id: int = 1, dataset_id: int = 1, storage_mode: str = "JSONB") -> MagicMock:
    row = MagicMock()
    row.id = id
    row.document_id = document_id
    row.dataset_id = dataset_id
    row.storage_mode = storage_mode
    return row


# ---------------------------------------------------------------------------
# GET /ocr-results
# ---------------------------------------------------------------------------

class TestListOcrResults:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/ocr-results").status_code == 200

    def test_returns_empty_list(self, client: TestClient) -> None:
        assert client.get("/ocr-results").json() == []

    def test_returns_list(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_ocr(id=1), _make_ocr(id=2)]
        data = client.get("/ocr-results").json()
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[1]["id"] == 2

    def test_response_contains_expected_fields(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_ocr(id=3, document_id=7, dataset_id=2)]
        data = client.get("/ocr-results").json()
        assert data[0]["document_id"] == 7
        assert data[0]["dataset_id"] == 2

    def test_filter_by_document_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_ocr(document_id=5)]
        data = client.get("/ocr-results?document_id=5").json()
        assert data[0]["document_id"] == 5


# ---------------------------------------------------------------------------
# GET /ocr-results/{ocr_id}
# ---------------------------------------------------------------------------

class TestGetOcrResult:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_ocr(id=1)
        assert client.get("/ocr-results/1").status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.get("/ocr-results/99").status_code == 404

    def test_response_contains_storage_mode(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_ocr(id=1, storage_mode="JSONB")
        data = client.get("/ocr-results/1").json()
        assert data["storage_mode"] == "JSONB"
        assert "document_id" in data

    def test_response_does_not_contain_dataset_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_ocr(id=1)
        data = client.get("/ocr-results/1").json()
        assert "dataset_id" not in data
