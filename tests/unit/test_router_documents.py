"""
Tests unitaires adam_api/routers/documents.py
"""
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.documents import router


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


def _make_document(
    id: int = 1,
    status: str = "RECEIVED",
    dataset_id: int = 1,
    file_id: int = 1,
) -> MagicMock:
    doc = MagicMock()
    doc.id = id
    doc.file_name = "doc.pdf"
    doc.status = status
    doc.dataset_id = dataset_id
    doc.file_id = file_id
    doc.metadata_ = {}
    doc.file = None
    doc.ocr_results = []
    doc.document_fields = []
    doc.jobs = []
    doc.page_count = None
    return doc


def _make_document_field(
    id: int = 1,
    document_id: int = 1,
    status: str = "pending",
) -> MagicMock:
    fs = MagicMock()
    fs.field_key = "deposant.nom"
    fs.display_label = "Nom"
    fs.section_id = "deposant"
    fs.section_label = "Deposant"
    fs.value_type = "text"
    fs.page = 1
    fs.display_order = 0

    df = MagicMock()
    df.id = id
    df.document_id = document_id
    df.field_spec = fs
    df.field_spec_id = 1
    df.group_id = None
    df.ocr_value = "MOULIN"
    df.resolved_value = None
    df.status = status
    df.ocr_confidence = 0.99
    df.ocr_polygon = None
    df.consensus_reached = False
    df.field_proposals = []
    return df


# ---------------------------------------------------------------------------
# GET /documents
# ---------------------------------------------------------------------------


class TestListDocuments:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/documents")
        assert response.status_code == 200

    def test_returns_list(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_document()]
        response = client.get("/documents")
        assert len(response.json()) == 1

    def test_page_count_from_file(self, client: TestClient, mock_db: AsyncMock) -> None:
        doc = _make_document()
        file = MagicMock()
        file.page_count = 12
        doc.file = file
        doc.page_count = 12
        mock_db.execute.return_value.scalars.return_value.all.return_value = [doc]
        response = client.get("/documents")
        assert response.json()[0]["page_count"] == 12

    def test_filter_by_dataset_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/documents?dataset_id=3")
        assert response.status_code == 200

    def test_filter_by_status(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/documents?status=VALIDATED")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /documents/{document_id}
# ---------------------------------------------------------------------------


class TestGetDocument:
    def test_returns_200_simple_view(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_document()
        response = client.get("/documents/1")
        assert response.status_code == 200

    def test_returns_200_full_view(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_document()
        response = client.get("/documents/1?view=full")
        assert response.status_code == 200

    def test_full_view_contains_pages(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_document()
        response = client.get("/documents/1?view=full")
        assert "pages" in response.json()

    def test_full_view_contains_jobs_and_ocr(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_document()
        response = client.get("/documents/1?view=full")
        body = response.json()
        assert "jobs" in body
        assert "ocr_results" in body

    def test_404_when_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/documents/99")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /documents/{document_id}/pages/{page_number}
# ---------------------------------------------------------------------------

# En-tete PNG minimal : suffit pour verifier les octets servis, pas besoin
# d'une image decodable.
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-image-payload"


def _make_document_with_file(file_id: int = 1, page_count: int = 3) -> MagicMock:
    doc = _make_document(file_id=file_id)
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
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_document()
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


# ---------------------------------------------------------------------------
# GET /documents/{document_id}/fields
# ---------------------------------------------------------------------------


class TestGetDocumentFields:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/documents/1/fields")
        assert response.status_code == 200

    def test_returns_fields(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_document_field()
        ]
        response = client.get("/documents/1/fields")
        assert len(response.json()) == 1

    def test_field_contains_expected_keys(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_document_field()
        ]
        response = client.get("/documents/1/fields")
        field = response.json()[0]
        for key in ("id", "document_id", "field_spec_id", "status", "consensus_reached", "value_type"):
            assert key in field

    def test_field_exposes_value_type(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_document_field()
        ]
        response = client.get("/documents/1/fields")
        assert response.json()[0]["value_type"] == "text"

    def test_boolean_field_returns_native_bool(self, client: TestClient, mock_db: AsyncMock) -> None:
        df = _make_document_field()
        df.field_spec.value_type = "BOOLEAN"
        df.ocr_value = "true"
        mock_db.execute.return_value.scalars.return_value.all.return_value = [df]
        response = client.get("/documents/1/fields")
        assert response.json()[0]["ocr_value"] is True

    def test_number_field_returns_native_int(self, client: TestClient, mock_db: AsyncMock) -> None:
        df = _make_document_field()
        df.field_spec.value_type = "NUMBER"
        df.ocr_value = "450000"
        mock_db.execute.return_value.scalars.return_value.all.return_value = [df]
        response = client.get("/documents/1/fields")
        assert response.json()[0]["ocr_value"] == 450000

    def test_number_non_convertible_returns_string(self, client: TestClient, mock_db: AsyncMock) -> None:
        df = _make_document_field()
        df.field_spec.value_type = "NUMBER"
        df.ocr_value = "12 BIS"
        mock_db.execute.return_value.scalars.return_value.all.return_value = [df]
        response = client.get("/documents/1/fields")
        assert response.json()[0]["ocr_value"] == "12 BIS"


# ---------------------------------------------------------------------------
# GET /documents/{document_id}/fields/by-section
# ---------------------------------------------------------------------------


class TestGetDocumentFieldsBySection:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/documents/1/fields/by-section")
        assert response.status_code == 200

    def test_groups_by_section(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_document_field()
        ]
        response = client.get("/documents/1/fields/by-section")
        body = response.json()
        assert "document_id" in body
        assert "sections" in body

    def test_section_contains_fields(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_document_field()
        ]
        response = client.get("/documents/1/fields/by-section")
        sections = response.json()["sections"]
        assert "deposant" in sections
        assert len(sections["deposant"]) == 1


# ---------------------------------------------------------------------------
# POST /documents
# ---------------------------------------------------------------------------


class TestCreateDocument:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.add = MagicMock()

        def capture_add(instance: object) -> None:
            instance.id = 1  # type: ignore[attr-defined]
            instance.file_name = "doc.pdf"  # type: ignore[attr-defined]
            instance.status = "RECEIVED"  # type: ignore[attr-defined]
            instance.dataset_id = 1  # type: ignore[attr-defined]
            instance.file_id = 1  # type: ignore[attr-defined]
            instance.metadata_ = {}  # type: ignore[attr-defined]
            instance.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)  # type: ignore[attr-defined]

        mock_db.add.side_effect = capture_add
        response = client.post(
            "/documents",
            json={"dataset_id": 1, "file_id": 1, "file_name": "doc.pdf"},
        )
        assert response.status_code == 201

    def test_422_when_missing_file_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.post("/documents", json={"dataset_id": 1, "file_name": "doc.pdf"})
        assert response.status_code == 422

    def test_422_when_missing_dataset_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.post("/documents", json={"file_id": 1, "file_name": "doc.pdf"})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /documents/{document_id}
# ---------------------------------------------------------------------------


class TestPatchDocument:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_document(
            status="RECEIVED"
        )
        response = client.patch("/documents/1", json={"status": "IN_PROGRESS"})
        assert response.status_code == 200

    def test_404_when_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.patch("/documents/99", json={"status": "IN_PROGRESS"})
        assert response.status_code == 404

    def test_409_on_status_conflict(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_document(
            status="IN_PROGRESS"
        )
        response = client.patch(
            "/documents/1",
            json={"status": "VALIDATED", "expected_current_status": "RECEIVED"},
        )
        assert response.status_code == 409


# ---------------------------------------------------------------------------
# PATCH /documents/{document_id}/fields/{field_id}
# ---------------------------------------------------------------------------


class TestPatchDocumentField:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_document_field()
        response = client.patch(
            "/documents/1/fields/1",
            json={"resolved_value": "MOULIN"},
        )
        assert response.status_code == 200

    def test_404_when_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = None
        response = client.patch("/documents/1/fields/99", json={"resolved_value": "X"})
        assert response.status_code == 404

    def test_404_when_field_belongs_to_other_document(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        mock_db.get.return_value = _make_document_field(document_id=99)
        response = client.patch("/documents/1/fields/1", json={"resolved_value": "X"})
        assert response.status_code == 404
