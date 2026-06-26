"""Tests unitaires du router /files."""
from tests.unit.conftest import SHA256, fake_doc, fake_file, make_result


# ---------------------------------------------------------------------------
# GET /files
# ---------------------------------------------------------------------------


class TestListFiles:
    def test_empty_list(self, client, mock_db):
        mock_db.execute.return_value = make_result(rows=[])
        resp = client.get("/files")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_files(self, client, mock_db):
        f = fake_file(id=3, file_path="/pvc/doc.pdf", page_count=7)
        mock_db.execute.return_value = make_result(rows=[f])
        resp = client.get("/files")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == 3
        assert data[0]["page_count"] == 7

    def test_filter_by_storage_type(self, client, mock_db):
        mock_db.execute.return_value = make_result(rows=[])
        resp = client.get("/files?storage_type=s3")
        assert resp.status_code == 200

    def test_multiple_files(self, client, mock_db):
        files = [fake_file(id=i) for i in range(1, 5)]
        mock_db.execute.return_value = make_result(rows=files)
        resp = client.get("/files")
        assert len(resp.json()) == 4


# ---------------------------------------------------------------------------
# GET /files/{id}
# ---------------------------------------------------------------------------


class TestGetFile:
    def test_not_found(self, client, mock_db):
        mock_db.execute.return_value = make_result(single=None)
        resp = client.get("/files/999")
        assert resp.status_code == 404

    def test_returns_detail(self, client, mock_db):
        f = fake_file(id=1, page_count=5, documents=[])
        mock_db.execute.return_value = make_result(single=f)
        resp = client.get("/files/1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1
        assert body["page_count"] == 5
        assert body["documents_count"] == 0

    def test_documents_count(self, client, mock_db):
        docs = [fake_doc(), fake_doc(id=2)]
        f = fake_file(id=1, documents=docs)
        mock_db.execute.return_value = make_result(single=f)
        resp = client.get("/files/1")
        assert resp.json()["documents_count"] == 2

    def test_storage_type_in_response(self, client, mock_db):
        f = fake_file(storage_type="s3", documents=[])
        mock_db.execute.return_value = make_result(single=f)
        resp = client.get("/files/1")
        assert resp.json()["storage_type"] == "s3"


# ---------------------------------------------------------------------------
# GET /files/{id}/documents
# ---------------------------------------------------------------------------


class TestGetFileDocuments:
    def test_file_not_found(self, client, mock_db):
        mock_db.get.return_value = None
        resp = client.get("/files/999/documents")
        assert resp.status_code == 404

    def test_returns_documents(self, client, mock_db):
        mock_db.get.return_value = fake_file()
        doc = fake_doc(id=5, file_name="x.pdf")
        mock_db.execute.return_value = make_result(rows=[doc])
        resp = client.get("/files/1/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == 5

    def test_returns_empty(self, client, mock_db):
        mock_db.get.return_value = fake_file()
        mock_db.execute.return_value = make_result(rows=[])
        resp = client.get("/files/1/documents")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# POST /files
# ---------------------------------------------------------------------------


class TestCreateFile:
    def test_invalid_checksum_too_short(self, client, mock_db):
        """sha256_checksum doit faire exactement 64 caractères."""
        mock_db.execute.return_value = make_result(single=None)
        resp = client.post(
            "/files",
            json={
                "file_path": "/pvc/a.pdf",
                "sha256_checksum": "abc",  # trop court
                "file_size_bytes": 1024,
            },
        )
        assert resp.status_code == 422

    def test_invalid_file_size_zero(self, client, mock_db):
        """file_size_bytes doit être > 0."""
        mock_db.execute.return_value = make_result(single=None)
        resp = client.post(
            "/files",
            json={
                "file_path": "/pvc/a.pdf",
                "sha256_checksum": SHA256,
                "file_size_bytes": 0,
            },
        )
        assert resp.status_code == 422

    def test_deduplication_returns_200(self, client, mock_db):
        """Si le sha256 existe déjà → 200 avec deduplicated=true."""
        existing = fake_file(id=5, sha256_checksum=SHA256)
        mock_db.execute.return_value = make_result(single=existing)
        resp = client.post(
            "/files",
            json={
                "file_path": "/pvc/nouveau.pdf",
                "sha256_checksum": SHA256,
                "file_size_bytes": 1024,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["deduplicated"] is True
        assert body["id"] == 5

    def test_missing_required_fields(self, client, mock_db):
        resp = client.post("/files", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /files/{id}
# ---------------------------------------------------------------------------


class TestPatchFile:
    def test_not_found(self, client, mock_db):
        mock_db.get.return_value = None
        resp = client.patch("/files/999", json={"file_path": "/pvc/new.pdf"})
        assert resp.status_code == 404

    def test_update_file_path(self, client, mock_db):
        f = fake_file(id=1, file_path="/pvc/old.pdf", page_count=3)
        mock_db.get.return_value = f
        resp = client.patch("/files/1", json={"file_path": "/pvc/new.pdf"})
        assert resp.status_code == 200
        assert resp.json()["file_path"] == "/pvc/new.pdf"

    def test_update_page_count(self, client, mock_db):
        f = fake_file(id=1, file_path="/pvc/doc.pdf", page_count=3)
        mock_db.get.return_value = f
        resp = client.patch("/files/1", json={"page_count": 10})
        assert resp.status_code == 200
        assert resp.json()["page_count"] == 10

    def test_invalid_page_count(self, client, mock_db):
        """page_count doit être >= 1."""
        resp = client.patch("/files/1", json={"page_count": 0})
        assert resp.status_code == 422

    def test_empty_patch_ok(self, client, mock_db):
        """PATCH avec payload vide est accepté (aucun champ requis)."""
        f = fake_file(id=1, file_path="/pvc/doc.pdf", page_count=3)
        mock_db.get.return_value = f
        resp = client.patch("/files/1", json={})
        assert resp.status_code == 200
