"""
Tests unitaires adam_api/routers/files.py
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.files import router

_NOW = datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc)


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


_SHA256 = "a" * 64


def _make_file(
    id: int = 1,
    file_path: str = "/pvc/doc.pdf",
    sha256_checksum: str = _SHA256,
    storage_type: str = "pvc",
) -> MagicMock:
    f = MagicMock()
    f.id = id
    f.file_path = file_path
    f.sha256_checksum = sha256_checksum
    f.storage_type = storage_type
    f.mime_type = "application/pdf"
    f.page_count = 1
    f.file_size_bytes = 1024
    f.created_at = _NOW
    f.documents = []
    return f


def _file_payload(**overrides: object) -> dict:
    base = {
        "file_path": "/pvc/doc.pdf",
        "sha256_checksum": _SHA256,
        "file_size_bytes": 1024,
        "page_count": 1,
        "mime_type": "application/pdf",
        "storage_type": "pvc",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# GET /files
# ---------------------------------------------------------------------------


class TestListFiles:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/files")
        assert response.status_code == 200

    def test_returns_list(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_file()]
        response = client.get("/files")
        assert len(response.json()) == 1

    def test_filter_by_storage_type(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/files?storage_type=s3")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /files/{file_id}
# ---------------------------------------------------------------------------


class TestGetFile:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_file()
        response = client.get("/files/1")
        assert response.status_code == 200

    def test_404_when_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/files/99")
        assert response.status_code == 404

    def test_response_contains_documents_count(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_file()
        response = client.get("/files/1")
        assert "documents_count" in response.json()


# ---------------------------------------------------------------------------
# GET /files/{file_id}/documents
# ---------------------------------------------------------------------------


class TestGetFileDocuments:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_file()
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        response = client.get("/files/1/documents")
        assert response.status_code == 200

    def test_404_when_file_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/files/99/documents")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /files
# ---------------------------------------------------------------------------


class TestCreateFile:
    def test_returns_201_new_file(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        mock_db.add = MagicMock()

        def capture_add(instance: object) -> None:
            instance.id = 1  # type: ignore[attr-defined]
            instance.file_path = "/pvc/doc.pdf"  # type: ignore[attr-defined]
            instance.sha256_checksum = _SHA256  # type: ignore[attr-defined]

        mock_db.add.side_effect = capture_add
        response = client.post("/files", json=_file_payload())
        assert response.status_code == 201
        assert response.json()["deduplicated"] is False

    def test_returns_200_deduplicated(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_file()
        response = client.post("/files", json=_file_payload())
        assert response.status_code == 200
        assert response.json()["deduplicated"] is True

    def test_invalid_sha256_length_rejected(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.post("/files", json=_file_payload(sha256_checksum="toocourt"))
        assert response.status_code == 422

    def test_invalid_file_size_rejected(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.post("/files", json=_file_payload(file_size_bytes=0))
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /files/{file_id}
# ---------------------------------------------------------------------------


class TestPatchFile:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_file()
        response = client.patch("/files/1", json={"file_path": "/pvc/nouveau.pdf"})
        assert response.status_code == 200

    def test_404_when_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.patch("/files/99", json={"file_path": "/pvc/x.pdf"})
        assert response.status_code == 404

    def test_update_page_count(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_file()
        response = client.patch("/files/1", json={"page_count": 10})
        assert response.status_code == 200
        assert response.json()["page_count"] == 10

    def test_invalid_page_count_rejected(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.patch("/files/1", json={"page_count": 0})
        assert response.status_code == 422
