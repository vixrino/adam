"""
Tests unitaires adam_api/routers/jobs.py
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.dependencies.auth import Caller, ServiceCaller, UserCaller, get_caller
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
def caller() -> Caller:
    """L'operateur 1, celui que _make_job() designe comme agent."""
    return UserCaller(matricule="MAT00002", organisation_id=1, user_id=1)


@pytest.fixture
def client(app: FastAPI, mock_db: AsyncMock, caller: Caller) -> TestClient:
    from adam_api.dependencies.db import get_db

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_caller] = lambda: caller
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

    def test_returns_the_existing_job_instead_of_creating_another(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        """Double clic / deux onglets : un agent n'a qu'un job non annule par document."""
        mock_db.get.return_value = _make_document()
        mock_db.add = MagicMock()
        existing = _make_job(id=7, state="IN_PROGRESS", step="VALIDATION", agent_id=1)
        mock_db.execute.return_value.scalar_one_or_none.return_value = existing

        response = client.post("/jobs", json=_job_payload())

        assert response.status_code == 200
        assert response.json()["id"] == 7
        mock_db.add.assert_not_called()

    def test_returns_the_existing_job_when_the_unique_index_refuses_a_duplicate(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        """Derniere defense : un doublon passe le verrou (ecriture hors endpoint), l'index le
        refuse, et l'appelant recoit le job existant au lieu d'un 500."""
        from sqlalchemy.exc import IntegrityError

        mock_db.get.return_value = _make_document()
        mock_db.add = MagicMock()
        mock_db.flush.side_effect = IntegrityError("INSERT", {}, Exception("uq_job_agent_document_active"))
        existing = _make_job(id=9, state="ASSIGNED")
        # 1st lookup (before creating) finds nothing; the 2nd one, after the refusal, finds it.
        mock_db.execute.side_effect = [
            _scalar_one_or_none(None),
            _scalar(0),
            _scalar_one_or_none(existing),
        ]

        response = client.post("/jobs", json=_job_payload())

        assert response.status_code == 200
        assert response.json()["id"] == 9
        mock_db.rollback.assert_awaited()

    def test_locks_the_document_while_checking(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_document()
        mock_db.add = MagicMock(side_effect=lambda i: setattr(i, "id", 1))

        client.post("/jobs", json=_job_payload())

        first = mock_db.get.call_args_list[0]
        assert first.kwargs.get("with_for_update") is True

    @pytest.mark.parametrize("status", ["RECEIVED", "INGESTED"])
    def test_409_while_the_document_is_not_ready(
        self, client: TestClient, mock_db: AsyncMock, status: str
    ) -> None:
        """Ses champs n'existent pas encore : un job y serait vide."""
        doc = _make_document()
        doc.status = status
        mock_db.get.return_value = doc
        mock_db.add = MagicMock()

        response = client.post("/jobs", json=_job_payload())

        assert response.status_code == 409
        mock_db.add.assert_not_called()

    @pytest.mark.parametrize(
        "status", ["IN_PROGRESS", "PENDING_CONSENSUS", "VALIDATED", "ERROR", "EXPORTED"]
    )
    def test_not_blocked_once_the_fields_exist(
        self, client: TestClient, mock_db: AsyncMock, status: str
    ) -> None:
        doc = _make_document()
        doc.status = status
        mock_db.get.return_value = doc
        mock_db.add = MagicMock(side_effect=lambda i: setattr(i, "id", 1))

        assert client.post("/jobs", json=_job_payload()).status_code == 201

    def test_404_when_document_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = None
        response = client.post("/jobs", json=_job_payload())
        assert response.status_code == 404

    def test_422_when_missing_fields(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.post("/jobs", json={})
        assert response.status_code == 422


def _scalar_one_or_none(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalar(value: int) -> MagicMock:
    """Resultat d'un SELECT count(...)."""
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def _field_of(job: MagicMock) -> MagicMock:
    """Un champ du document du job (la proposition sur un champ etranger est refusee)."""
    field = MagicMock()
    field.document_id = job.document_id
    return field


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
        mock_db.get.side_effect = [job, _field_of(job)]
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

    def test_does_not_write_the_proposal_on_the_shared_field(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        job = _make_job(state="IN_PROGRESS")
        field = _field_of(job)
        field.resolved_value = "OCR"
        field.status = "PENDING"
        mock_db.get.side_effect = [job, field]
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        mock_db.add = MagicMock(side_effect=lambda i: setattr(i, "id", 1))

        client.post("/jobs/1/propose", json=self._payload())

        assert field.resolved_value == "OCR"
        assert field.status == "PENDING"

    def test_updates_existing_proposal(self, client: TestClient, mock_db: AsyncMock) -> None:
        job = _make_job(state="IN_PROGRESS")
        existing_proposal = MagicMock()
        existing_proposal.id = 5
        existing_proposal.step = "VALIDATION"
        existing_proposal.value = "ANCIEN"
        existing_proposal.value_type = "text"
        mock_db.get.side_effect = [job, _field_of(job)]
        mock_db.execute.return_value.scalar_one_or_none.return_value = existing_proposal
        response = client.post("/jobs/1/propose", json=self._payload())
        assert response.status_code == 201


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/propose/bulk
# ---------------------------------------------------------------------------


class TestProposeBulk:
    @staticmethod
    def _field(id: int, document_id: int = 1) -> MagicMock:
        df = MagicMock()
        df.id = id
        df.document_id = document_id
        return df

    @staticmethod
    def _rows(items: list) -> MagicMock:
        result = MagicMock()
        result.scalars.return_value.all.return_value = items
        return result

    def _setup(
        self,
        mock_db: AsyncMock,
        job: MagicMock,
        fields: list,
        existing: list | None = None,
    ) -> list:
        mock_db.get.return_value = job
        mock_db.execute.side_effect = [self._rows(fields), self._rows(existing or [])]
        added: list = []
        mock_db.add = MagicMock(side_effect=lambda obj: (setattr(obj, "id", 100 + len(added)), added.append(obj)))
        return added

    @staticmethod
    def _body(*items: tuple) -> dict:
        return {
            "proposals": [
                {"document_field_id": fid, "value": value, "value_type": "TEXT"} for fid, value in items
            ]
        }

    def test_creates_one_proposal_per_field_in_one_call(self, client: TestClient, mock_db: AsyncMock) -> None:
        job = _make_job(state="ASSIGNED", document_id=1)
        added = self._setup(mock_db, job, [self._field(1), self._field(2)])

        response = client.post("/jobs/1/propose/bulk", json=self._body((1, "A"), (2, None)))

        assert response.status_code == 201
        assert [p["document_field_id"] for p in response.json()] == [1, 2]
        assert [p["value"] for p in response.json()] == ["A", None]
        assert len(added) == 2
        assert job.state == "IN_PROGRESS"

    def test_updates_existing_proposals_instead_of_duplicating(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        job = _make_job(state="IN_PROGRESS", document_id=1)
        old = MagicMock()
        old.id = 5
        old.job_id = 1
        old.step = "VALIDATION"
        old.document_field_id = 1
        old.value = "ANCIEN"
        old.value_type = "TEXT"
        added = self._setup(mock_db, job, [self._field(1), self._field(2)], existing=[old])

        response = client.post("/jobs/1/propose/bulk", json=self._body((1, "NOUVEAU"), (2, "B")))

        assert response.status_code == 201
        assert old.value == "NOUVEAU"
        assert len(added) == 1  # only field 2 is new

    def test_leaves_the_shared_document_field_untouched(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        """La valeur retenue est celle du consensus : une proposition ne doit pas etre visible
        du second operateur dans le champ partage."""
        f1 = self._field(1)
        f1.resolved_value = "OCR"
        f1.status = "PENDING"
        self._setup(mock_db, _make_job(document_id=1), [f1])

        client.post("/jobs/1/propose/bulk", json=self._body((1, "A")))

        assert f1.resolved_value == "OCR"
        assert f1.status == "PENDING"

    def test_same_field_twice_keeps_the_last_value(self, client: TestClient, mock_db: AsyncMock) -> None:
        added = self._setup(mock_db, _make_job(document_id=1), [self._field(1)])

        response = client.post("/jobs/1/propose/bulk", json=self._body((1, "A"), (1, "B")))

        assert response.status_code == 201
        assert len(added) == 1
        assert added[0].value == "B"

    def test_404_when_a_field_is_unknown_and_nothing_is_written(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        job = _make_job(state="ASSIGNED", document_id=1)
        added = self._setup(mock_db, job, [self._field(1)])  # field 2 not returned

        response = client.post("/jobs/1/propose/bulk", json=self._body((1, "A"), (2, "B")))

        assert response.status_code == 404
        assert added == []
        assert job.state == "ASSIGNED"

    def test_422_when_a_field_belongs_to_another_document(self, client: TestClient, mock_db: AsyncMock) -> None:
        job = _make_job(state="ASSIGNED", document_id=1)
        added = self._setup(mock_db, job, [self._field(1), self._field(2, document_id=99)])

        response = client.post("/jobs/1/propose/bulk", json=self._body((1, "A"), (2, "B")))

        assert response.status_code == 422
        assert added == []
        assert job.state == "ASSIGNED"

    def test_404_when_the_job_does_not_exist(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = None
        assert client.post("/jobs/9/propose/bulk", json=self._body((1, "A"))).status_code == 404

    @pytest.mark.parametrize("state", ["SUBMITTED", "CANCELLED"])
    def test_409_when_the_job_is_closed(self, client: TestClient, mock_db: AsyncMock, state: str) -> None:
        mock_db.get.return_value = _make_job(state=state)
        assert client.post("/jobs/1/propose/bulk", json=self._body((1, "A"))).status_code == 409

    def test_422_on_an_empty_batch(self, client: TestClient) -> None:
        assert client.post("/jobs/1/propose/bulk", json={"proposals": []}).status_code == 422


# ---------------------------------------------------------------------------
# PATCH /jobs/{job_id}/submit
# ---------------------------------------------------------------------------


class TestSubmitJob:
    def _setup_db(self, mock_db: AsyncMock, state: str = "IN_PROGRESS") -> MagicMock:
        job = _make_job(state=state)
        dataset = MagicMock()
        dataset.required_operators = 2
        # get() order in submit_job: job, document (locked), dataset
        mock_db.get.side_effect = [job, MagicMock(), dataset]
        mock_db.execute.side_effect = [_scalar(0), _scalar(1)]  # unreviewed fields, submitted jobs
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


class TestSubmitConsensusTrigger:
    """Le consensus doit voir le submit qui complete le quorum."""

    @staticmethod
    def _wire(mock_db: AsyncMock, required: int, submitted: int) -> tuple:
        job = _make_job(state="IN_PROGRESS")
        document = MagicMock()
        document.status = "IN_PROGRESS"
        dataset = MagicMock()
        dataset.required_operators = required
        mock_db.get.side_effect = [job, document, dataset]
        mock_db.execute.side_effect = [_scalar(0), _scalar(submitted)]  # unreviewed, submitted
        return job, document

    def test_commits_before_the_consensus_task_runs(
        self, client: TestClient, mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """La tache de fond tourne avant le commit de la session de la requete : sans commit
        explicite elle compte un job de moins que le quorum et ne valide jamais le document."""
        order: list[str] = []
        self._wire(mock_db, required=2, submitted=2)
        mock_db.commit.side_effect = lambda: order.append("commit")

        async def fake_resolve(document_id: int, dataset_id: int) -> None:
            order.append("try_resolve")

        monkeypatch.setattr("adam_api.routers.jobs.try_resolve", fake_resolve)

        response = client.patch("/jobs/1/submit")

        assert response.status_code == 200
        assert order == ["commit", "try_resolve"]

    def test_marks_the_document_pending_consensus_at_quorum(
        self, client: TestClient, mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("adam_api.routers.jobs.try_resolve", AsyncMock())
        _, document = self._wire(mock_db, required=2, submitted=2)

        client.patch("/jobs/1/submit")

        assert document.status == "PENDING_CONSENSUS"

    def test_does_not_trigger_the_consensus_below_the_quorum(
        self, client: TestClient, mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        resolve = AsyncMock()
        monkeypatch.setattr("adam_api.routers.jobs.try_resolve", resolve)
        _, document = self._wire(mock_db, required=2, submitted=1)

        response = client.patch("/jobs/1/submit")

        assert response.status_code == 200
        resolve.assert_not_called()
        assert document.status == "IN_PROGRESS"

    def test_locks_the_job_and_its_document(self, client: TestClient, mock_db: AsyncMock) -> None:
        """Un submit a la fois par document : sans verrou, deux operateurs simultanes comptent
        chacun '1/2' et le consensus n'est jamais declenche."""
        self._wire(mock_db, required=2, submitted=1)

        client.patch("/jobs/1/submit")

        locked = [c for c in mock_db.get.call_args_list if c.kwargs.get("with_for_update") is True]
        assert len(locked) == 2  # the job, then its document


class TestJobOwnership:
    """Seul l'operateur du job propose et soumet sur son job."""

    @pytest.mark.parametrize(
        "caller",
        [
            UserCaller(matricule="MAT00005", organisation_id=1, user_id=2),
            UserCaller(matricule="MAT00003", organisation_id=1, user_id=3, platform_role="NOTA_ADMIN"),
            ServiceCaller(service_name="internal-service"),
        ],
        ids=["another-operator", "platform-admin", "service"],
    )
    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("post", "/jobs/1/propose", {"document_field_id": 1, "value": "x"}),
            ("post", "/jobs/1/propose/bulk", {"proposals": [{"document_field_id": 1, "value": "x"}]}),
            ("patch", "/jobs/1/submit", None),
        ],
        ids=["propose", "bulk", "submit"],
    )
    def test_refuses_anyone_but_the_jobs_agent(
        self, client: TestClient, mock_db: AsyncMock, method: str, path: str, body: dict | None
    ) -> None:
        mock_db.get.return_value = _make_job(state="IN_PROGRESS", agent_id=1)

        response = getattr(client, method)(path, **({"json": body} if body is not None else {}))

        assert response.status_code == 403
        mock_db.add.assert_not_called()

    def test_the_agent_can_propose(self, client: TestClient, mock_db: AsyncMock) -> None:
        field = MagicMock()
        field.document_id = 1
        mock_db.get.side_effect = [_make_job(state="IN_PROGRESS", agent_id=1, document_id=1), field]
        mock_db.add = MagicMock(side_effect=lambda i: setattr(i, "id", 1))

        response = client.post("/jobs/1/propose", json={"document_field_id": 1, "value": "x"})

        assert response.status_code == 201


class TestProposeForeignField:
    def test_422_when_the_field_belongs_to_another_document(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        field = MagicMock()
        field.document_id = 99
        mock_db.get.side_effect = [_make_job(state="IN_PROGRESS", agent_id=1, document_id=1), field]
        mock_db.add = MagicMock()

        response = client.post("/jobs/1/propose", json={"document_field_id": 5, "value": "x"})

        assert response.status_code == 422
        mock_db.add.assert_not_called()


class TestSubmitRequiresReview:
    """Un champ avec une valeur doit avoir ete verifie (proposition) avant le submit."""

    def test_409_when_fields_with_a_value_have_no_proposal(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        job = _make_job(state="IN_PROGRESS")
        mock_db.get.side_effect = [job, MagicMock(), MagicMock()]
        mock_db.execute.side_effect = [_scalar(3)]

        response = client.patch("/jobs/1/submit")

        assert response.status_code == 409
        assert "3 champ" in response.json()["detail"]
        assert job.state == "IN_PROGRESS"  # untouched

    def test_a_disputed_field_must_be_settled_even_when_it_has_no_value(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        """Deux avis opposes sur un champ sans valeur OCR : le litige doit etre tranche, meme si
        le champ est vide (la regle "a une valeur" seule le laisserait passer)."""
        mock_db.get.side_effect = [_make_job(state="IN_PROGRESS"), MagicMock(), MagicMock()]
        mock_db.execute.side_effect = [_scalar(1)]

        client.patch("/jobs/1/submit")

        statement = mock_db.execute.call_args_list[0].args[0]
        sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
        assert "document_field.status = 'DISPUTED'" in sql
        assert "consensus_reached IS false" in sql.replace("IS NOT", "IS") or "consensus_reached" in sql

    def test_does_not_commit_nor_trigger_the_consensus_when_refused(
        self, client: TestClient, mock_db: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        resolve = AsyncMock()
        monkeypatch.setattr("adam_api.routers.jobs.try_resolve", resolve)
        mock_db.get.side_effect = [_make_job(state="IN_PROGRESS"), MagicMock(), MagicMock()]
        mock_db.execute.side_effect = [_scalar(1)]

        client.patch("/jobs/1/submit")

        mock_db.commit.assert_not_called()
        resolve.assert_not_called()

    def test_empty_fields_do_not_block_the_submit(self, client: TestClient, mock_db: AsyncMock) -> None:
        dataset = MagicMock()
        dataset.required_operators = 2
        mock_db.get.side_effect = [_make_job(state="IN_PROGRESS"), MagicMock(), dataset]
        mock_db.execute.side_effect = [_scalar(0), _scalar(1)]

        assert client.patch("/jobs/1/submit").status_code == 200


class TestJobDetailIsPrivate:
    """Le detail d'un job porte les propositions de son operateur : lui seul le lit."""

    @pytest.mark.parametrize(
        "caller",
        [
            UserCaller(matricule="MAT00005", organisation_id=1, user_id=2),
            UserCaller(matricule="MAT00001", organisation_id=1, user_id=9),  # business admin
            UserCaller(matricule="MAT00003", organisation_id=1, user_id=3, platform_role="NOTA_ADMIN"),
            ServiceCaller(service_name="internal-service"),
        ],
        ids=["another-operator", "business-admin", "platform-admin", "service"],
    )
    def test_refuses_anyone_but_the_jobs_agent(self, client: TestClient, mock_db: AsyncMock) -> None:
        job = _make_job(agent_id=1)
        mock_db.execute.return_value.scalar_one_or_none.return_value = job

        response = client.get("/jobs/1")

        assert response.status_code == 403
        assert "pages" not in response.json()

    def test_the_agent_reads_their_own_job(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_job(agent_id=1)

        assert client.get("/jobs/1").status_code == 200

    def test_404_before_anything_else_when_the_job_does_not_exist(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        assert client.get("/jobs/99").status_code == 404
