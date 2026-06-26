"""Tests unitaires du router /jobs."""
from tests.unit.conftest import (
    fake_doc,
    fake_document_field,
    fake_field_proposal,
    fake_job,
    fake_user,
    make_result,
)


# ---------------------------------------------------------------------------
# GET /jobs
# ---------------------------------------------------------------------------


class TestListJobs:
    def test_empty_list(self, client, mock_db):
        mock_db.execute.return_value = make_result(rows=[])
        resp = client.get("/jobs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_jobs(self, client, mock_db):
        job = fake_job(id=7, state="ASSIGNED", step="VALIDATION")
        mock_db.execute.return_value = make_result(rows=[job])
        resp = client.get("/jobs")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == 7
        assert data[0]["state"] == "ASSIGNED"

    def test_filter_by_agent_id(self, client, mock_db):
        mock_db.execute.return_value = make_result(rows=[])
        resp = client.get("/jobs?agent_id=5")
        assert resp.status_code == 200

    def test_filter_by_state(self, client, mock_db):
        mock_db.execute.return_value = make_result(rows=[])
        resp = client.get("/jobs?state=SUBMITTED")
        assert resp.status_code == 200

    def test_filter_by_dataset(self, client, mock_db):
        mock_db.execute.return_value = make_result(rows=[])
        resp = client.get("/jobs?dataset_id=3")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /jobs/{id}
# ---------------------------------------------------------------------------


class TestGetJob:
    def test_not_found(self, client, mock_db):
        mock_db.execute.return_value = make_result(single=None)
        resp = client.get("/jobs/999")
        assert resp.status_code == 404

    def test_returns_detail_empty_pages(self, client, mock_db):
        doc = fake_doc(document_fields=[])
        job = fake_job(id=1, document=doc, field_proposals=[])
        mock_db.execute.return_value = make_result(single=job)
        resp = client.get("/jobs/1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1
        assert body["state"] == "ASSIGNED"
        assert body["pages"] == []

    def test_returns_detail_with_fields(self, client, mock_db):
        df = fake_document_field(id=10, field_key="nom", section_id="s1", page=1)
        doc = fake_doc(document_fields=[df])
        proposal = fake_field_proposal(document_field_id=10, value="Martin")
        job = fake_job(id=1, document=doc, field_proposals=[proposal], step="VALIDATION")
        mock_db.execute.return_value = make_result(single=job)
        resp = client.get("/jobs/1")
        assert resp.status_code == 200
        pages = resp.json()["pages"]
        assert len(pages) == 1
        assert pages[0]["page"] == 1
        field = pages[0]["sections"][0]["fields"][0]
        assert field["field_key"] == "nom"
        assert field["value"] == "Martin"


# ---------------------------------------------------------------------------
# POST /jobs
# ---------------------------------------------------------------------------


class TestCreateJob:
    def test_missing_fields(self, client, mock_db):
        resp = client.post("/jobs", json={})
        assert resp.status_code == 422

    def test_document_not_found(self, client, mock_db):
        mock_db.get.side_effect = [None]  # document introuvable
        resp = client.post(
            "/jobs", json={"dataset_id": 1, "document_id": 999, "agent_id": 1}
        )
        assert resp.status_code == 404

    def test_agent_not_found(self, client, mock_db):
        doc = fake_doc()
        mock_db.get.side_effect = [doc, None]  # doc ok, user introuvable
        mock_db.execute.return_value = make_result(scalar=0)
        resp = client.post(
            "/jobs", json={"dataset_id": 1, "document_id": 1, "agent_id": 999}
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /jobs/{id}/propose
# ---------------------------------------------------------------------------


class TestProposeFieldValue:
    def test_job_not_found(self, client, mock_db):
        mock_db.get.side_effect = [None]
        resp = client.post(
            "/jobs/999/propose", json={"document_field_id": 1, "value": "test"}
        )
        assert resp.status_code == 404

    def test_job_already_submitted(self, client, mock_db):
        job = fake_job(state="SUBMITTED")
        mock_db.get.side_effect = [job]
        resp = client.post(
            "/jobs/1/propose", json={"document_field_id": 1, "value": "test"}
        )
        assert resp.status_code == 409

    def test_job_cancelled(self, client, mock_db):
        job = fake_job(state="CANCELLED")
        mock_db.get.side_effect = [job]
        resp = client.post(
            "/jobs/1/propose", json={"document_field_id": 1, "value": "test"}
        )
        assert resp.status_code == 409

    def test_document_field_not_found(self, client, mock_db):
        job = fake_job(state="ASSIGNED")
        df_none = None
        mock_db.get.side_effect = [job, df_none]
        mock_db.execute.return_value = make_result(single=None)
        resp = client.post(
            "/jobs/1/propose", json={"document_field_id": 999, "value": "test"}
        )
        assert resp.status_code == 404

    def test_missing_document_field_id(self, client, mock_db):
        """Payload sans document_field_id → 422."""
        resp = client.post("/jobs/1/propose", json={"value": "test"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /jobs/{id}/submit
# ---------------------------------------------------------------------------


class TestSubmitJob:
    def test_not_found(self, client, mock_db):
        mock_db.get.side_effect = [None]
        resp = client.patch("/jobs/999/submit")
        assert resp.status_code == 404

    def test_already_submitted(self, client, mock_db):
        job = fake_job(state="SUBMITTED")
        mock_db.get.side_effect = [job]
        resp = client.patch("/jobs/1/submit")
        assert resp.status_code == 409

    def test_already_cancelled(self, client, mock_db):
        job = fake_job(state="CANCELLED")
        mock_db.get.side_effect = [job]
        resp = client.patch("/jobs/1/submit")
        assert resp.status_code == 409
