"""Tests unitaires du router /datasets."""
from tests.unit.conftest import fake_dataset, make_result


# ---------------------------------------------------------------------------
# GET /datasets
# ---------------------------------------------------------------------------


class TestListDatasets:
    def test_empty_list(self, client, mock_db):
        mock_db.execute.return_value = make_result(rows=[])
        resp = client.get("/datasets")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_datasets(self, client, mock_db):
        ds = fake_dataset(id=4, name="Lot 2025", status="ACTIVE")
        mock_db.execute.return_value = make_result(rows=[ds])
        resp = client.get("/datasets")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == 4
        assert data[0]["name"] == "Lot 2025"

    def test_filter_by_project_id(self, client, mock_db):
        mock_db.execute.return_value = make_result(rows=[])
        resp = client.get("/datasets?project_id=2")
        assert resp.status_code == 200

    def test_filter_by_status(self, client, mock_db):
        mock_db.execute.return_value = make_result(rows=[])
        resp = client.get("/datasets?status=DRAFT")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /datasets/{id}
# ---------------------------------------------------------------------------


class TestGetDataset:
    def test_not_found(self, client, mock_db):
        mock_db.get.return_value = None
        resp = client.get("/datasets/999")
        assert resp.status_code == 404

    def test_returns_dataset(self, client, mock_db):
        ds = fake_dataset(id=1, name="DS Test", ocr_provider="PULSAR", required_operators=3)
        mock_db.get.return_value = ds
        resp = client.get("/datasets/1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1
        assert body["name"] == "DS Test"
        assert body["required_operators"] == 3


# ---------------------------------------------------------------------------
# GET /datasets/{id}/stats
# ---------------------------------------------------------------------------


class TestGetDatasetStats:
    def test_not_found(self, client, mock_db):
        mock_db.get.return_value = None
        resp = client.get("/datasets/999/stats")
        assert resp.status_code == 404

    def test_returns_stats(self, client, mock_db):
        ds = fake_dataset(id=1)
        mock_db.get.return_value = ds
        # Deux appels à execute : total puis validated
        r_total = make_result(scalar=20)
        r_validated = make_result(scalar=5)
        mock_db.execute.side_effect = [r_total, r_validated]
        resp = client.get("/datasets/1/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["dataset_id"] == 1
        assert body["documents_total"] == 20
        assert body["documents_validated"] == 5

    def test_zero_documents(self, client, mock_db):
        ds = fake_dataset(id=1)
        mock_db.get.return_value = ds
        mock_db.execute.side_effect = [make_result(scalar=0), make_result(scalar=0)]
        resp = client.get("/datasets/1/stats")
        body = resp.json()
        assert body["documents_total"] == 0
        assert body["documents_validated"] == 0


# ---------------------------------------------------------------------------
# POST /datasets
# ---------------------------------------------------------------------------


class TestCreateDataset:
    def test_missing_required_fields(self, client, mock_db):
        resp = client.post("/datasets", json={})
        assert resp.status_code == 422

    def test_missing_schema_id(self, client, mock_db):
        resp = client.post(
            "/datasets",
            json={"project_id": 1, "name": "DS"},
        )
        assert resp.status_code == 422

    def test_required_operators_out_of_range(self, client, mock_db):
        """required_operators doit être entre 1 et 5."""
        resp = client.post(
            "/datasets",
            json={
                "project_id": 1,
                "schema_id": 1,
                "name": "DS",
                "required_operators": 10,  # > 5
            },
        )
        assert resp.status_code == 422

    def test_required_operators_zero(self, client, mock_db):
        resp = client.post(
            "/datasets",
            json={
                "project_id": 1,
                "schema_id": 1,
                "name": "DS",
                "required_operators": 0,  # < 1
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /datasets/{id}
# ---------------------------------------------------------------------------


class TestPatchDataset:
    def test_not_found(self, client, mock_db):
        mock_db.get.return_value = None
        resp = client.patch("/datasets/999", json={"name": "Nouveau nom"})
        assert resp.status_code == 404

    def test_update_name(self, client, mock_db):
        ds = fake_dataset(id=1, name="Ancien nom")
        mock_db.get.return_value = ds
        resp = client.patch("/datasets/1", json={"name": "Nouveau nom"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Nouveau nom"

    def test_required_operators_out_of_range(self, client, mock_db):
        resp = client.patch("/datasets/1", json={"required_operators": 99})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /datasets/{id}/status
# ---------------------------------------------------------------------------


class TestPatchDatasetStatus:
    def test_invalid_status(self, client, mock_db):
        resp = client.patch("/datasets/1/status?status=INVALID_STATUS")
        assert resp.status_code == 422

    def test_not_found(self, client, mock_db):
        mock_db.get.return_value = None
        resp = client.patch("/datasets/999/status?status=ACTIVE")
        assert resp.status_code == 404

    def test_valid_status_change(self, client, mock_db):
        ds = fake_dataset(id=1, status="DRAFT")
        mock_db.get.return_value = ds
        resp = client.patch("/datasets/1/status?status=ACTIVE")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ACTIVE"
