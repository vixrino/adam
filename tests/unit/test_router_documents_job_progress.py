"""Test autonome : GET /documents/{id}/job-progress.

A deposer tel quel dans tests/unit/ de nota. Ne depend d'aucun helper ou
fixture du test_router_documents.py existant : il cree ses propres app,
mock_db et client. Teste les 4 CA de l'endpoint de suivi de progression.
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


def _make_document(status: str = "RECEIVED") -> MagicMock:
    doc = MagicMock()
    doc.id = 1
    doc.status = status
    doc.jobs = []
    return doc


def _make_job(id: int = 1, state: str = "IN_PROGRESS", step: str = "VALIDATION") -> MagicMock:
    job = MagicMock()
    job.id = id
    job.state = state
    job.step = step
    return job


def _set_doc(mock_db: AsyncMock, doc: MagicMock) -> None:
    mock_db.execute.return_value.scalar_one_or_none.return_value = doc


class TestGetDocumentJobProgress:
    def test_404_when_document_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        # CA-4 : document introuvable -> 404
        assert client.get("/documents/99/job-progress").status_code == 404

    def test_active_job_returns_continue_and_step(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        # CA-1 / CA-2 / CA-3
        doc = _make_document(status="IN_PROGRESS")
        doc.jobs = [_make_job(id=5, state="IN_PROGRESS", step="CONSENSUS")]
        _set_doc(mock_db, doc)
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
        _set_doc(mock_db, doc)
        body = client.get("/documents/1/job-progress").json()
        assert body["has_active_job"] is True
        assert body["action"] == "CONTINUE"

    def test_no_active_job_but_validated_returns_review(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        # CA-3 : pas de job actif, document valide -> REVIEW
        doc = _make_document(status="VALIDATED")
        doc.jobs = [_make_job(state="SUBMITTED")]
        _set_doc(mock_db, doc)
        body = client.get("/documents/1/job-progress").json()
        assert body["has_active_job"] is False
        assert body["step"] is None
        assert body["action"] == "REVIEW"

    def test_submitted_job_returns_review(self, client: TestClient, mock_db: AsyncMock) -> None:
        doc = _make_document(status="IN_PROGRESS")
        doc.jobs = [_make_job(state="SUBMITTED")]
        _set_doc(mock_db, doc)
        assert client.get("/documents/1/job-progress").json()["action"] == "REVIEW"

    def test_no_job_returns_unavailable(self, client: TestClient, mock_db: AsyncMock) -> None:
        # CA-4 : pas de job actif -> 200 explicite (distinct du 404)
        doc = _make_document(status="RECEIVED")
        doc.jobs = []
        _set_doc(mock_db, doc)
        response = client.get("/documents/1/job-progress")
        assert response.status_code == 200
        body = response.json()
        assert body["has_active_job"] is False
        assert body["action"] == "UNAVAILABLE"

    def test_cancelled_job_is_not_active(self, client: TestClient, mock_db: AsyncMock) -> None:
        doc = _make_document(status="RECEIVED")
        doc.jobs = [_make_job(state="CANCELLED")]
        _set_doc(mock_db, doc)
        body = client.get("/documents/1/job-progress").json()
        assert body["has_active_job"] is False
        assert body["action"] == "UNAVAILABLE"

    def test_most_recent_active_job_wins(self, client: TestClient, mock_db: AsyncMock) -> None:
        doc = _make_document(status="IN_PROGRESS")
        doc.jobs = [
            _make_job(id=1, state="IN_PROGRESS", step="VALIDATION"),
            _make_job(id=4, state="IN_PROGRESS", step="CONSENSUS"),
        ]
        _set_doc(mock_db, doc)
        body = client.get("/documents/1/job-progress").json()
        assert body["active_job_id"] == 4
        assert body["step"] == "CONSENSUS"
