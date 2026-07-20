"""Tests unitaires de GET /documents/{id}/pages/{n} (endpoint images de pages).

Fichier autonome : a deposer tel quel dans tests/unit/ de adam (ou a fusionner
dans son test_router_documents.py existant). Ne depend d'aucun schema de
reponse — uniquement du router et de settings.pvc_mount_path.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.documents import router


@pytest.fixture
def app() -> FastAPI:
    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    return fastapi_app


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result
    return db


@pytest.fixture
def client(app: FastAPI, mock_db: AsyncMock) -> TestClient:
    from adam_api.dependencies.db import get_db

    app.dependency_overrides[get_db] = lambda: mock_db
    return TestClient(app, raise_server_exceptions=False)


# En-tete PNG minimal : suffit pour verifier les octets servis, pas besoin
# d'une image decodable.
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-image-payload"


def _make_document_with_file(file_id: int = 1, page_count: int = 3) -> MagicMock:
    doc = MagicMock()
    doc.id = 1
    file = MagicMock()
    file.id = file_id
    file.page_count = page_count
    doc.file = file
    return doc


class TestGetDocumentPageImage:
    @pytest.fixture(autouse=True)
    def pvc_root(self, tmp_path, monkeypatch):
        from adam_api.core.config import settings

        monkeypatch.setattr(settings, "pvc_mount_path", str(tmp_path))
        return tmp_path

    def _write_page_image(self, pvc_root, file_id: int, page_number: int) -> None:
        pages_dir = pvc_root / str(file_id) / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        (pages_dir / f"{page_number:04d}.png").write_bytes(_PNG_BYTES)

    # CA-1 / CA-2
    def test_returns_png_bytes_with_content_type(
        self, client: TestClient, mock_db: AsyncMock, pvc_root
    ) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_document_with_file()
        self._write_page_image(pvc_root, file_id=1, page_number=2)
        response = client.get("/documents/1/pages/2")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content == _PNG_BYTES

    def test_404_when_document_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/documents/99/pages/1")
        assert response.status_code == 404

    def test_404_when_document_has_no_file(self, client: TestClient, mock_db: AsyncMock) -> None:
        doc = MagicMock()
        doc.file = None
        mock_db.execute.return_value.scalar_one_or_none.return_value = doc
        response = client.get("/documents/1/pages/1")
        assert response.status_code == 404

    # CA-3
    def test_404_when_images_not_generated(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_document_with_file()
        response = client.get("/documents/1/pages/1")
        assert response.status_code == 404
        assert "non generees" in response.json()["detail"]

    # CA-4
    def test_404_when_page_above_page_count(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_document_with_file(
            page_count=3
        )
        response = client.get("/documents/1/pages/4")
        assert response.status_code == 404
        assert "hors bornes" in response.json()["detail"]

    def test_404_when_page_zero(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_document_with_file()
        response = client.get("/documents/1/pages/0")
        assert response.status_code == 404
