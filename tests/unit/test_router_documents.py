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
# GET /documents/{document_id}/job-progress
# ---------------------------------------------------------------------------


def _make_job(id: int = 1, state: str = "IN_PROGRESS", step: str = "VALIDATION") -> MagicMock:
    job = MagicMock()
    job.id = id
    job.state = state
    job.step = step
    return job


class TestGetDocumentJobProgress:
    def test_404_when_document_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        # CA-4 : document introuvable -> 404
        response = client.get("/documents/99/job-progress")
        assert response.status_code == 404

    def test_active_job_returns_continue_and_step(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        # CA-1 / CA-2 / CA-3
        doc = _make_document()
        doc.status = "IN_PROGRESS"
        doc.jobs = [_make_job(id=5, state="IN_PROGRESS", step="CONSENSUS")]
        mock_db.execute.return_value.scalar_one_or_none.return_value = doc
        response = client.get("/documents/1/job-progress")
        assert response.status_code == 200
        body = response.json()
        assert body["has_active_job"] is True
        assert body["active_job_id"] == 5
        assert body["step"] == "CONSENSUS"
        assert body["action"] == "CONTINUE"

    def test_assigned_job_is_active(self, client: TestClient, mock_db: AsyncMock) -> None:
        doc = _make_document()
        doc.jobs = [_make_job(id=3, state="ASSIGNED", step="VALIDATION")]
        mock_db.execute.return_value.scalar_one_or_none.return_value = doc
        body = client.get("/documents/1/job-progress").json()
        assert body["has_active_job"] is True
        assert body["action"] == "CONTINUE"

    def test_no_active_job_but_validated_returns_review(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        # CA-3 : pas de job actif, document valide -> REVIEW
        doc = _make_document(status="VALIDATED")
        doc.jobs = [_make_job(state="SUBMITTED")]
        mock_db.execute.return_value.scalar_one_or_none.return_value = doc
        body = client.get("/documents/1/job-progress").json()
        assert body["has_active_job"] is False
        assert body["step"] is None
        assert body["action"] == "REVIEW"

    def test_submitted_job_returns_review(self, client: TestClient, mock_db: AsyncMock) -> None:
        doc = _make_document(status="IN_PROGRESS")
        doc.jobs = [_make_job(state="SUBMITTED")]
        mock_db.execute.return_value.scalar_one_or_none.return_value = doc
        body = client.get("/documents/1/job-progress").json()
        assert body["action"] == "REVIEW"

    def test_no_job_returns_unavailable(self, client: TestClient, mock_db: AsyncMock) -> None:
        # CA-4 : pas de job actif -> 200 explicite (distinct du 404)
        doc = _make_document(status="RECEIVED")
        doc.jobs = []
        mock_db.execute.return_value.scalar_one_or_none.return_value = doc
        response = client.get("/documents/1/job-progress")
        assert response.status_code == 200
        body = response.json()
        assert body["has_active_job"] is False
        assert body["action"] == "UNAVAILABLE"

    def test_cancelled_job_is_not_active(self, client: TestClient, mock_db: AsyncMock) -> None:
        doc = _make_document(status="RECEIVED")
        doc.jobs = [_make_job(state="CANCELLED")]
        mock_db.execute.return_value.scalar_one_or_none.return_value = doc
        body = client.get("/documents/1/job-progress").json()
        assert body["has_active_job"] is False
        assert body["action"] == "UNAVAILABLE"

    def test_most_recent_active_job_wins(self, client: TestClient, mock_db: AsyncMock) -> None:
        doc = _make_document(status="IN_PROGRESS")
        doc.jobs = [
            _make_job(id=1, state="IN_PROGRESS", step="VALIDATION"),
            _make_job(id=4, state="IN_PROGRESS", step="CONSENSUS"),
        ]
        mock_db.execute.return_value.scalar_one_or_none.return_value = doc
        body = client.get("/documents/1/job-progress").json()
        assert body["active_job_id"] == 4
        assert body["step"] == "CONSENSUS"


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
