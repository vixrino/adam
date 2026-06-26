"""
Tests unitaires adam_api/routers/datasets.py
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.datasets import router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app() -> FastAPI:
    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    return fastapi_app


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = []
    execute_result.scalar_one_or_none.return_value = None
    execute_result.all.return_value = []
    db.execute.return_value = execute_result
    db.get.return_value = None
    return db


@pytest.fixture
def client(app: FastAPI, mock_db: AsyncMock) -> TestClient:
    from adam_api.dependencies.db import get_db
    app.dependency_overrides[get_db] = lambda: mock_db
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_dataset(
    id: int = 1,
    name: str = "Dataset A",
    status: str = "draft",
    project_id: int = 1,
    schema_id: int = 1,
) -> MagicMock:
    ds = MagicMock()
    ds.id = id
    ds.name = name
    ds.status = status
    ds.project_id = project_id
    ds.schema_id = schema_id
    ds.description = None
    ds.ocr_provider = "pulsar"
    ds.ocr_model_id = None
    ds.required_operators = 2
    ds.ocr_job_enabled = True
    ds.configs = {}
    ds.documents = []
    ds.created_at = None
    ds.updated_at = None
    return ds


def _dataset_payload(**overrides: object) -> dict:
    base = {
        "project_id": 1,
        "schema_id": 1,
        "name": "Dataset A",
        "required_operators": 2,
        "ocr_job_enabled": True,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# GET /datasets
# ---------------------------------------------------------------------------


class TestListDatasets:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/datasets")
        assert response.status_code == 200

    def test_returns_list(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_dataset()]
        response = client.get("/datasets")
        assert len(response.json()) == 1

    def test_filter_by_project_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/datasets?project_id=2")
        assert response.status_code == 200

    def test_filter_by_status(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/datasets?status=ACTIVE")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /datasets/{dataset_id}
# ---------------------------------------------------------------------------


class TestGetDataset:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_dataset()
        response = client.get("/datasets/1")
        assert response.status_code == 200

    def test_404_when_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/datasets/99")
        assert response.status_code == 404

    def test_response_contains_required_fields(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        mock_db.get.return_value = _make_dataset()
        response = client.get("/datasets/1")
        body = response.json()
        for field in ("id", "name", "status", "required_operators", "ocr_job_enabled"):
            assert field in body


# ---------------------------------------------------------------------------
# GET /datasets/{dataset_id}/stats
# ---------------------------------------------------------------------------


class TestGetDatasetStats:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_dataset()
        mock_db.execute.return_value.all.return_value = []
        response = client.get("/datasets/1/stats")
        assert response.status_code == 200

    def test_404_when_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/datasets/99/stats")
        assert response.status_code == 404

    def test_stats_contain_expected_fields(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        mock_db.get.return_value = _make_dataset()
        mock_db.execute.return_value.all.return_value = []
        response = client.get("/datasets/1/stats")
        body = response.json()
        for field in ("dataset_id", "documents_total", "documents_validated"):
            assert field in body


# ---------------------------------------------------------------------------
# POST /datasets
# ---------------------------------------------------------------------------


class TestCreateDataset:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.add = MagicMock()

        def capture_add(instance: object) -> None:
            instance.id = 1  # type: ignore[attr-defined]
            instance.name = "Dataset A"  # type: ignore[attr-defined]
            instance.status = "draft"  # type: ignore[attr-defined]
            instance.project_id = 1  # type: ignore[attr-defined]
            instance.schema_id = 1  # type: ignore[attr-defined]
            instance.description = None  # type: ignore[attr-defined]
            instance.ocr_provider = "pulsar"  # type: ignore[attr-defined]
            instance.required_operators = 2  # type: ignore[attr-defined]
            instance.ocr_job_enabled = True  # type: ignore[attr-defined]

        mock_db.add.side_effect = capture_add
        response = client.post("/datasets", json=_dataset_payload())
        assert response.status_code == 201

    def test_invalid_required_operators_rejected(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        response = client.post("/datasets", json=_dataset_payload(required_operators=10))
        assert response.status_code == 422

    def test_422_when_missing_schema_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.post("/datasets", json={"project_id": 1, "name": "DS"})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /datasets/{dataset_id}
# ---------------------------------------------------------------------------


class TestPatchDataset:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_dataset()
        response = client.patch("/datasets/1", json={"name": "Nouveau Nom"})
        assert response.status_code == 200

    def test_404_when_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = None
        response = client.patch("/datasets/99", json={"name": "X"})
        assert response.status_code == 404

    def test_422_on_invalid_status(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_dataset()
        response = client.patch("/datasets/1", json={"required_operators": 99})
        assert response.status_code == 422
