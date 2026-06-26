"""Tests unitaires du router /documents."""
from unittest.mock import MagicMock

from tests.unit.conftest import (
    fake_doc,
    fake_document_field,
    fake_file,
    make_result,
)


# ---------------------------------------------------------------------------
# GET /documents
# ---------------------------------------------------------------------------


class TestListDocuments:
    def test_empty_list(self, client, mock_db):
        mock_db.execute.return_value = make_result(rows=[])
        resp = client.get("/documents")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_documents(self, client, mock_db):
        doc = fake_doc(id=7, file_name="rapport.pdf", status="RECEIVED")
        mock_db.execute.return_value = make_result(rows=[doc])
        resp = client.get("/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == 7
        assert data[0]["file_name"] == "rapport.pdf"
        assert data[0]["status"] == "RECEIVED"

    def test_page_count_from_file(self, client, mock_db):
        """CA-2 : page_count est remonté depuis le File associé."""
        doc = fake_doc(page_count=12)
        mock_db.execute.return_value = make_result(rows=[doc])
        resp = client.get("/documents")
        assert resp.json()[0]["page_count"] == 12

    def test_multiple_documents(self, client, mock_db):
        docs = [
            fake_doc(id=1, file_name="a.pdf"),
            fake_doc(id=2, file_name="b.pdf"),
            fake_doc(id=3, file_name="c.pdf"),
        ]
        mock_db.execute.return_value = make_result(rows=docs)
        resp = client.get("/documents")
        assert len(resp.json()) == 3

    def test_filter_by_dataset_id(self, client, mock_db):
        mock_db.execute.return_value = make_result(rows=[])
        resp = client.get("/documents?dataset_id=3")
        assert resp.status_code == 200

    def test_filter_by_status(self, client, mock_db):
        mock_db.execute.return_value = make_result(rows=[])
        resp = client.get("/documents?status=VALIDATED")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /documents/{id}
# ---------------------------------------------------------------------------


class TestGetDocument:
    def test_not_found(self, client, mock_db):
        mock_db.execute.return_value = make_result(single=None)
        resp = client.get("/documents/999")
        assert resp.status_code == 404

    def test_simple_view_returns_document(self, client, mock_db):
        """Le page_count est lu depuis doc.file.page_count (simple view)."""
        file = fake_file(page_count=5)
        doc = fake_doc(id=3, status="IN_PROGRESS", file=file)
        mock_db.execute.return_value = make_result(single=doc)
        resp = client.get("/documents/3")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 3
        assert body["status"] == "IN_PROGRESS"
        assert body["page_count"] == 5

    def test_full_view_empty_fields(self, client, mock_db):
        doc = fake_doc(id=1, document_fields=[], ocr_results=[], jobs=[])
        mock_db.execute.return_value = make_result(single=doc)
        resp = client.get("/documents/1?view=full")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pages"] == []
        assert body["ocr_results"] == []
        assert body["jobs"] == []

    def test_full_view_with_jobs(self, client, mock_db):
        job_mock = MagicMock()
        job_mock.id = 99
        job_mock.state = "SUBMITTED"
        doc = fake_doc(jobs=[job_mock], document_fields=[], ocr_results=[])
        mock_db.execute.return_value = make_result(single=doc)
        resp = client.get("/documents/1?view=full")
        assert resp.status_code == 200
        jobs = resp.json()["jobs"]
        assert len(jobs) == 1
        assert jobs[0]["id"] == 99
        assert jobs[0]["state"] == "SUBMITTED"

    def test_full_view_with_ocr_results(self, client, mock_db):
        ocr = MagicMock()
        ocr.id = 77
        doc = fake_doc(ocr_results=[ocr], document_fields=[], jobs=[])
        mock_db.execute.return_value = make_result(single=doc)
        resp = client.get("/documents/1?view=full")
        assert resp.json()["ocr_results"][0]["id"] == 77

    def test_full_view_file_ref(self, client, mock_db):
        file = fake_file(id=5, file_path="/pvc/doc.pdf")
        doc = fake_doc(file=file, document_fields=[], ocr_results=[], jobs=[])
        mock_db.execute.return_value = make_result(single=doc)
        resp = client.get("/documents/1?view=full")
        file_body = resp.json()["file"]
        assert file_body["id"] == 5
        assert file_body["path"] == "/pvc/doc.pdf"


# ---------------------------------------------------------------------------
# GET /documents/{id}/fields
# ---------------------------------------------------------------------------


class TestGetDocumentFields:
    def test_empty(self, client, mock_db):
        mock_db.execute.return_value = make_result(rows=[])
        resp = client.get("/documents/1/fields")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_with_fields(self, client, mock_db):
        df = fake_document_field(id=5, status="CORRECTED", resolved_value="Dupont")
        mock_db.execute.return_value = make_result(rows=[df])
        resp = client.get("/documents/1/fields")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == 5
        assert data[0]["status"] == "CORRECTED"
        assert data[0]["resolved_value"] == "Dupont"

    def test_field_with_polygon(self, client, mock_db):
        df = fake_document_field(ocr_polygon=[0.1, 0.2, 0.8, 0.9])
        mock_db.execute.return_value = make_result(rows=[df])
        resp = client.get("/documents/1/fields")
        assert resp.json()[0]["ocr_polygon"] == [0.1, 0.2, 0.8, 0.9]


# ---------------------------------------------------------------------------
# GET /documents/{id}/fields/by-section
# ---------------------------------------------------------------------------


class TestGetDocumentFieldsBySection:
    def test_empty_sections(self, client, mock_db):
        mock_db.execute.return_value = make_result(rows=[])
        resp = client.get("/documents/1/fields/by-section")
        assert resp.status_code == 200
        body = resp.json()
        assert body["document_id"] == 1
        assert body["sections"] == {}

    def test_grouped_by_section(self, client, mock_db):
        df1 = fake_document_field(id=1, field_key="nom", section_id="s1")
        df2 = fake_document_field(id=2, field_key="prenom", section_id="s1")
        df3 = fake_document_field(id=3, field_key="date", section_id="s2")
        mock_db.execute.return_value = make_result(rows=[df1, df2, df3])
        resp = client.get("/documents/42/fields/by-section")
        assert resp.status_code == 200
        body = resp.json()
        assert body["document_id"] == 42
        assert len(body["sections"]["s1"]) == 2
        assert len(body["sections"]["s2"]) == 1

    def test_section_field_keys(self, client, mock_db):
        df = fake_document_field(id=10, field_key="iban", section_id="paiement")
        mock_db.execute.return_value = make_result(rows=[df])
        resp = client.get("/documents/1/fields/by-section")
        item = resp.json()["sections"]["paiement"][0]
        assert item["id"] == 10
        assert item["field_key"] == "iban"


# ---------------------------------------------------------------------------
# POST /documents
# ---------------------------------------------------------------------------


class TestCreateDocument:
    def test_missing_required_fields(self, client, mock_db):
        """Payload vide → 422 Unprocessable Entity."""
        resp = client.post("/documents", json={})
        assert resp.status_code == 422

    def test_missing_file_id(self, client, mock_db):
        resp = client.post("/documents", json={"dataset_id": 1, "file_name": "x.pdf"})
        assert resp.status_code == 422

    def test_missing_dataset_id(self, client, mock_db):
        resp = client.post("/documents", json={"file_id": 1, "file_name": "x.pdf"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /documents/{id}
# ---------------------------------------------------------------------------


class TestPatchDocument:
    def test_not_found(self, client, mock_db):
        mock_db.execute.return_value = make_result(single=None)
        resp = client.patch("/documents/999", json={"status": "VALIDATED"})
        assert resp.status_code == 404

    def test_status_conflict(self, client, mock_db):
        """expected_current_status ne correspond pas → 409."""
        doc = fake_doc(status="RECEIVED")
        mock_db.execute.return_value = make_result(single=doc)
        resp = client.patch(
            "/documents/1",
            json={"status": "VALIDATED", "expected_current_status": "IN_PROGRESS"},
        )
        assert resp.status_code == 409

    def test_status_update_ok(self, client, mock_db):
        doc = fake_doc(id=1, status="RECEIVED")
        mock_db.execute.return_value = make_result(single=doc)
        resp = client.patch("/documents/1", json={"status": "VALIDATED"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "VALIDATED"

    def test_no_conflict_check_when_unset(self, client, mock_db):
        """Sans expected_current_status, la mise à jour passe toujours."""
        doc = fake_doc(status="IN_PROGRESS")
        mock_db.execute.return_value = make_result(single=doc)
        resp = client.patch("/documents/1", json={"status": "VALIDATED"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# PATCH /documents/{id}/fields/{field_id}
# ---------------------------------------------------------------------------


class TestPatchDocumentField:
    def test_field_not_found(self, client, mock_db):
        mock_db.get.return_value = None
        resp = client.patch("/documents/1/fields/999", json={"status": "CORRECTED"})
        assert resp.status_code == 404

    def test_wrong_document_id(self, client, mock_db):
        """Champ appartenant à un autre document → 404."""
        df = fake_document_field(id=1, document_id=99)
        mock_db.get.return_value = df
        resp = client.patch("/documents/1/fields/1", json={"status": "CORRECTED"})
        assert resp.status_code == 404

    def test_update_resolved_value(self, client, mock_db):
        df = fake_document_field(id=1, document_id=1, status="CORRECTED", resolved_value="Dupont")
        mock_db.get.return_value = df
        resp = client.patch(
            "/documents/1/fields/1",
            json={"resolved_value": "Dupont", "status": "CORRECTED"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1
        assert body["status"] == "CORRECTED"
        assert body["resolved_value"] == "Dupont"

    def test_partial_update_consensus(self, client, mock_db):
        df = fake_document_field(id=2, document_id=1, status="PENDING", consensus_reached=False)
        mock_db.get.return_value = df
        resp = client.patch("/documents/1/fields/2", json={"consensus_reached": True})
        assert resp.status_code == 200
