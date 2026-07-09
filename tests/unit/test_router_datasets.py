"""
Tests unitaires adam_api/routers/datasets.py
"""
from pathlib import Path

import pymupdf
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.datasets import router
from adam_core.models import Dataset, DocSchema, Organisation, Project


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


def _make_schema(id: int = 1, document_type: str = "cerfa") -> MagicMock:
    s = MagicMock()
    s.id = id
    s.document_type = document_type
    return s


def _make_project(id: int = 1, organisation_id: int = 1) -> MagicMock:
    p = MagicMock()
    p.id = id
    p.organisation_id = organisation_id
    return p


def _make_organisation(id: int = 1, slug: str = "dires") -> MagicMock:
    o = MagicMock()
    o.id = id
    o.slug = slug
    return o


def _db_get_side_effect(
    dataset: object = None,
    schema: object = None,
    project: object = None,
    organisation: object = None,
):
    """Dispatch db.get(Model, id) selon Model, pour mocker les lookups
    dataset/schema/project/organisation de l'endpoint d'ingestion."""
    by_model = {
        Dataset: dataset,
        DocSchema: schema if schema is not None else _make_schema(),
        Project: project if project is not None else _make_project(),
        Organisation: organisation if organisation is not None else _make_organisation(),
    }

    async def _get(model: object, _id: object) -> object:
        return by_model.get(model)

    return _get


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


# ---------------------------------------------------------------------------
# POST /datasets/{dataset_id}/documents
# ---------------------------------------------------------------------------


def _minimal_valid_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def _exec_result(
    scalar_one_or_none: object = None,
    scalar_one: object = None,
    one_or_none: object = None,
) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.one_or_none.return_value = one_or_none
    if scalar_one is not None:
        result.scalar_one.return_value = scalar_one
    return result


def _capture_document_id(instance: object) -> None:
    if type(instance).__name__ == "Document":
        instance.id = 42  # type: ignore[attr-defined]


class TestIngestDocuments:
    def test_404_when_dataset_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = None
        response = client.post(
            "/datasets/99/documents",
            files=[("files", ("doc.pdf", _minimal_valid_pdf(), "application/pdf"))],
        )
        assert response.status_code == 404

    def test_new_file_returns_200_and_created(
        self,
        client: TestClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("adam_api.routers.datasets.settings.pvc_mount_path", str(tmp_path))
        mock_db.get = AsyncMock(side_effect=_db_get_side_effect(dataset=_make_dataset()))
        mock_db.add = MagicMock(side_effect=_capture_document_id)
        new_file = MagicMock()
        new_file.id = 7
        new_file.file_path = "dires/cerfa/2026_01_15_1321/doc.pdf"
        mock_db.execute = AsyncMock(
            side_effect=[
                _exec_result(scalar_one_or_none=None),  # existing document (dataset+checksum) -> aucun
                _exec_result(scalar_one_or_none=None),  # File existant par checksum -> aucun
                _exec_result(scalar_one_or_none=new_file),  # INSERT ... RETURNING -> cree
            ]
        )

        response = client.post(
            "/datasets/1/documents",
            files=[("files", ("doc.pdf", _minimal_valid_pdf(), "application/pdf"))],
        )

        assert response.status_code == 200
        body = response.json()
        assert body["created"] == 1
        assert body["already_exists"] == 0
        assert body["rejected"] == 0
        assert body["results"][0]["file_name"] == "doc.pdf"
        assert body["results"][0]["status"] == "created"

    def test_duplicate_file_in_dataset_returns_already_exists(
        self,
        client: TestClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("adam_api.routers.datasets.settings.pvc_mount_path", str(tmp_path))
        mock_db.get = AsyncMock(side_effect=_db_get_side_effect(dataset=_make_dataset()))
        existing_doc = MagicMock()
        existing_doc.id = 10
        existing_doc.file_id = 3
        mock_db.execute = AsyncMock(
            side_effect=[
                _exec_result(one_or_none=(existing_doc, "dires/cerfa/2026_01_01_0000/doc.pdf")),  # deja lie dans ce dataset
            ]
        )

        response = client.post(
            "/datasets/1/documents",
            files=[("files", ("doc.pdf", _minimal_valid_pdf(), "application/pdf"))],
        )

        assert response.status_code == 200
        body = response.json()
        assert body["created"] == 0
        assert body["already_exists"] == 1
        assert body["results"][0]["status"] == "already_exists"
        assert body["results"][0]["document_id"] == 10

    def test_non_pdf_content_rejected(
        self,
        client: TestClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("adam_api.routers.datasets.settings.pvc_mount_path", str(tmp_path))
        mock_db.get = AsyncMock(side_effect=_db_get_side_effect(dataset=_make_dataset()))

        response = client.post(
            "/datasets/1/documents",
            files=[("files", ("fake.pdf", b"not a real pdf", "application/pdf"))],
        )

        assert response.status_code == 200
        body = response.json()
        assert body["created"] == 0
        assert body["rejected"] == 1
        assert body["results"][0]["status"] == "rejected"
        assert body["results"][0]["reason"] == "non-PDF"
        # aucun appel DB pour un fichier rejete avant meme la validation
        mock_db.execute.assert_not_awaited()

    def test_multiple_files_detailed_per_file(
        self,
        client: TestClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("adam_api.routers.datasets.settings.pvc_mount_path", str(tmp_path))
        mock_db.get = AsyncMock(side_effect=_db_get_side_effect(dataset=_make_dataset()))
        mock_db.add = MagicMock(side_effect=_capture_document_id)
        new_file = MagicMock()
        new_file.id = 7
        new_file.file_path = "dires/cerfa/2026_01_15_1321/doc.pdf"
        mock_db.execute = AsyncMock(
            side_effect=[
                _exec_result(scalar_one_or_none=None),  # existing doc check (fichier 1)
                _exec_result(scalar_one_or_none=None),  # File select (fichier 1)
                _exec_result(scalar_one_or_none=new_file),  # INSERT RETURNING (fichier 1)
            ]
        )

        response = client.post(
            "/datasets/1/documents",
            files=[
                ("files", ("valid.pdf", _minimal_valid_pdf(), "application/pdf")),
                ("files", ("invalid.pdf", b"garbage", "application/pdf")),
            ],
        )

        assert response.status_code == 200
        body = response.json()
        assert body["received"] == 2
        assert body["created"] == 1
        assert body["rejected"] == 1
        statuses = {r["file_name"]: r["status"] for r in body["results"]}
        assert statuses["valid.pdf"] == "created"
        assert statuses["invalid.pdf"] == "rejected"
