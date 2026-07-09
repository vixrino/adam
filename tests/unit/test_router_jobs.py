"""
Tests unitaires adam_api/routers/jobs.py
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.jobs import router

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
    execute_result.scalar_one.return_value = 0
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


def _make_job(
    id: int = 1,
    state: str = "ASSIGNED",
    step: str = "VALIDATION",
    agent_id: int = 1,
    document_id: int = 1,
    dataset_id: int = 1,
) -> MagicMock:
    job = MagicMock()
    job.id = id
    job.state = state
    job.step = step
    job.agent_id = agent_id
    job.document_id = document_id
    job.dataset_id = dataset_id
    job.started_at = _NOW
    job.submitted_at = None
    job.created_at = _NOW
    job.document = _make_document()
    job.document.document_fields = []
    job.field_proposals = []
    return job


def _make_document(id: int = 1) -> MagicMock:
    doc = MagicMock()
    doc.id = id
    doc.document_fields = []
    return doc


def _job_payload(**overrides: object) -> dict:
    base = {
        "dataset_id": 1,
        "document_id": 1,
        "agent_id": 1,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# GET /jobs
# ---------------------------------------------------------------------------


class TestListJobs:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/jobs")
        assert response.status_code == 200

    def test_returns_list(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_job()]
        response = client.get("/jobs")
        assert len(response.json()) == 1

    def test_filter_by_agent_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/jobs?agent_id=5")
        assert response.status_code == 200

    def test_filter_by_state(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/jobs?state=SUBMITTED")
        assert response.status_code == 200

    def test_filter_by_dataset(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/jobs?dataset_id=3")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}
# ---------------------------------------------------------------------------


class TestGetJob:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_job()
        response = client.get("/jobs/1")
        assert response.status_code == 200

    def test_404_when_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/jobs/99")
        assert response.status_code == 404

    def test_response_contains_pages(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_job()
        response = client.get("/jobs/1")
        assert "pages" in response.json()


# ---------------------------------------------------------------------------
# POST /jobs
# ---------------------------------------------------------------------------


class TestCreateJob:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_document()
        mock_db.add = MagicMock()

        def capture_add(instance: object) -> None:
            instance.id = 1  # type: ignore[attr-defined]
            instance.state = "ASSIGNED"  # type: ignore[attr-defined]
            instance.step = "VALIDATION"  # type: ignore[attr-defined]
            instance.agent_id = 1  # type: ignore[attr-defined]
            instance.document_id = 1  # type: ignore[attr-defined]
            instance.dataset_id = 1  # type: ignore[attr-defined]

        mock_db.add.side_effect = capture_add
        response = client.post("/jobs", json=_job_payload())
        assert response.status_code == 201

    def test_404_when_document_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = None
        response = client.post("/jobs", json=_job_payload())
        assert response.status_code == 404

    def test_422_when_missing_fields(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.post("/jobs", json={})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/propose
# ---------------------------------------------------------------------------


class TestProposeFieldValue:
    def _payload(self) -> dict:
        return {"document_field_id": 1, "value": "MOULIN", "value_type": "text"}

    def test_404_when_job_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = None
        response = client.post("/jobs/99/propose", json=self._payload())
        assert response.status_code == 404

    def test_409_when_already_SUBMITTED(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_job(state="SUBMITTED")
        response = client.post("/jobs/1/propose", json=self._payload())
        assert response.status_code == 409

    def test_409_when_CANCELLED(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_job(state="CANCELLED")
        response = client.post("/jobs/1/propose", json=self._payload())
        assert response.status_code == 409

    def test_returns_201_new_proposal(self, client: TestClient, mock_db: AsyncMock) -> None:
        job = _make_job(state="ASSIGNED")
        mock_db.get.side_effect = [job, MagicMock()]
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        mock_db.add = MagicMock()

        def capture_add(instance: object) -> None:
            instance.id = 10  # type: ignore[attr-defined]
            instance.step = "VALIDATION"  # type: ignore[attr-defined]
            instance.value = "MOULIN"  # type: ignore[attr-defined]
            instance.value_type = "text"  # type: ignore[attr-defined]

        mock_db.add.side_effect = capture_add
        response = client.post("/jobs/1/propose", json=self._payload())
        assert response.status_code == 201

    def test_updates_existing_proposal(self, client: TestClient, mock_db: AsyncMock) -> None:
        job = _make_job(state="IN_PROGRESS")
        existing_proposal = MagicMock()
        existing_proposal.id = 5
        existing_proposal.step = "VALIDATION"
        existing_proposal.value = "ANCIEN"
        existing_proposal.value_type = "text"
        mock_db.get.side_effect = [job, MagicMock()]
        mock_db.execute.return_value.scalar_one_or_none.return_value = existing_proposal
        response = client.post("/jobs/1/propose", json=self._payload())
        assert response.status_code == 201


# ---------------------------------------------------------------------------
# PATCH /jobs/{job_id}/submit
# ---------------------------------------------------------------------------


class TestSubmitJob:
    def _setup_db(self, mock_db: AsyncMock, state: str = "IN_PROGRESS") -> MagicMock:
        job = _make_job(state=state)
        dataset = MagicMock()
        dataset.required_operators = 2
        mock_db.get.side_effect = [job, dataset, MagicMock()]
        mock_db.execute.return_value.scalar_one.return_value = 1
        return job

    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        self._setup_db(mock_db)
        response = client.patch("/jobs/1/submit")
        assert response.status_code == 200

    def test_404_when_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = None
        response = client.patch("/jobs/99/submit")
        assert response.status_code == 404

    def test_409_when_already_submitted(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_job(state="SUBMITTED")
        response = client.patch("/jobs/1/submit")
        assert response.status_code == 409

    def test_409_when_cancelled(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_job(state="CANCELLED")
        response = client.patch("/jobs/1/submit")
        assert response.status_code == 409

    def test_response_contains_state_and_submitted_at(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        self._setup_db(mock_db)
        response = client.patch("/jobs/1/submit")
        body = response.json()
        assert "state" in body
        assert "submitted_at" in body
