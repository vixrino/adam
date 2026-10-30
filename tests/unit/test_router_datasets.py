"""
Tests unitaires adam_api/routers/datasets.py
"""

from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.routers.datasets import router
from adam_core.enums.roles import PlatformRole
from adam_core.models import Dataset, DocSchema, Document, Job, Organisation, Project

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


def _make_dataset(
    id: int = 1,
    name: str = "Dataset A",
    status: str = "draft",
    project_id: int = 1,
    schema_id: int = 1,
    expected_page_count: Optional[int] = None,
) -> MagicMock:
    ds = MagicMock()
    ds.id = id
    ds.expected_page_count = expected_page_count
    ds.name = name
    ds.status = status
    ds.project_id = project_id
    ds.schema_id = schema_id
    ds.description = None
    ds.ocr_provider = "pulsar"
    ds.ocr_model_id = None
    ds.required_operators = 2
    ds.ocr_job_enabled = True
    ds.configs = {}
    ds.documents = []
    ds.created_at = None
    ds.updated_at = None
    return ds


def _make_schema(id: int = 1, document_type: str = "cerfa") -> MagicMock:
    s = MagicMock()
    s.id = id
    s.document_type = document_type
    return s


def _make_project(id: int = 1, organisation_id: int = 1) -> MagicMock:
    p = MagicMock()
    p.id = id
    p.organisation_id = organisation_id
    return p


def _make_organisation(id: int = 1, slug: str = "dires") -> MagicMock:
    o = MagicMock()
    o.id = id
    o.slug = slug
    return o


def _db_get_side_effect(
    dataset: object = None,
    schema: object = None,
    project: object = None,
    organisation: object = None,
):
    """Dispatch db.get(Model, id) selon Model, pour mocker les lookups
    dataset/schema/project/organisation de l'endpoint d'ingestion."""
    by_model = {
        Dataset: dataset,
        DocSchema: schema if schema is not None else _make_schema(),
        Project: project if project is not None else _make_project(),
        Organisation: organisation if organisation is not None else _make_organisation(),
    }

    async def _get(model: object, _id: object) -> object:
        return by_model.get(model)

    return _get


def _dataset_payload(**overrides: object) -> dict:
    base = {
        "project_id": 1,
        "schema_id": 1,
        "name": "Dataset A",
        "required_operators": 2,
        "ocr_job_enabled": True,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# GET /datasets
# ---------------------------------------------------------------------------


class TestListDatasets:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/datasets")
        assert response.status_code == 200

    def test_returns_list(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [_make_dataset()]
        response = client.get("/datasets")
        assert len(response.json()) == 1

    def test_filter_by_project_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/datasets?project_id=2")
        assert response.status_code == 200

    def test_filter_by_status(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/datasets?status=ACTIVE")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /datasets/{dataset_id}
# ---------------------------------------------------------------------------


class TestGetDataset:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_dataset()
        response = client.get("/datasets/1")
        assert response.status_code == 200

    def test_404_when_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/datasets/99")
        assert response.status_code == 404

    def test_response_contains_required_fields(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        mock_db.get.return_value = _make_dataset()
        response = client.get("/datasets/1")
        body = response.json()
        for field in ("id", "name", "status", "required_operators", "ocr_job_enabled"):
            assert field in body


# ---------------------------------------------------------------------------
# GET /datasets/{dataset_id}/stats
# ---------------------------------------------------------------------------


class TestGetDatasetStats:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_dataset()
        mock_db.execute.return_value.all.return_value = []
        response = client.get("/datasets/1/stats")
        assert response.status_code == 200

    def test_404_when_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.get("/datasets/99/stats")
        assert response.status_code == 404

    def test_stats_contain_expected_fields(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_dataset()
        mock_db.execute.return_value.all.return_value = []
        response = client.get("/datasets/1/stats")
        body = response.json()
        for field in ("dataset_id", "documents_total", "documents_validated"):
            assert field in body


# ---------------------------------------------------------------------------
# POST /datasets
# ---------------------------------------------------------------------------


class TestCreateDataset:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.add = MagicMock()

        def capture_add(instance: object) -> None:
            instance.id = 1  # type: ignore[attr-defined]
            instance.name = "Dataset A"  # type: ignore[attr-defined]
            instance.status = "draft"  # type: ignore[attr-defined]
            instance.project_id = 1  # type: ignore[attr-defined]
            instance.schema_id = 1  # type: ignore[attr-defined]
            instance.description = None  # type: ignore[attr-defined]
            instance.ocr_provider = "pulsar"  # type: ignore[attr-defined]
            instance.required_operators = 2  # type: ignore[attr-defined]
            instance.ocr_job_enabled = True  # type: ignore[attr-defined]

        mock_db.add.side_effect = capture_add
        response = client.post("/datasets", json=_dataset_payload())
        assert response.status_code == 201

    def test_invalid_required_operators_rejected(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        response = client.post("/datasets", json=_dataset_payload(required_operators=10))
        assert response.status_code == 422

    def test_422_when_missing_schema_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        response = client.post("/datasets", json={"project_id": 1, "name": "DS"})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# PATCH /datasets/{dataset_id}
# ---------------------------------------------------------------------------


class TestPatchDataset:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_dataset()
        response = client.patch("/datasets/1", json={"name": "Nouveau Nom"})
        assert response.status_code == 200

    def test_404_when_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = None
        response = client.patch("/datasets/99", json={"name": "X"})
        assert response.status_code == 404

    def test_422_on_invalid_status(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_dataset()
        response = client.patch("/datasets/1", json={"required_operators": 99})
        assert response.status_code == 422

    def test_409_when_changing_schema_of_a_non_draft_dataset(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        mock_db.get.return_value = _make_dataset(status="ACTIVE", schema_id=1)
        response = client.patch("/datasets/1", json={"schema_id": 2})
        assert response.status_code == 409

    def test_schema_change_accepted_on_draft_even_if_target_is_locked(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        draft = _make_dataset(status="DRAFT", schema_id=1)
        locked_schema = MagicMock(locked=True)
        mock_db.get = AsyncMock(side_effect=[draft, locked_schema])
        mock_db.execute.return_value.scalar_one.return_value = 0
        response = client.patch("/datasets/1", json={"schema_id": 2})
        assert response.status_code == 200
        assert draft.schema_id == 2


# ---------------------------------------------------------------------------
# POST /datasets/{dataset_id}/documents
# ---------------------------------------------------------------------------


def _minimal_valid_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def _exec_result(
    scalar_one_or_none: object = None,
    scalar_one: object = None,
    one_or_none: object = None,
) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    result.one_or_none.return_value = one_or_none
    if scalar_one is not None:
        result.scalar_one.return_value = scalar_one
    return result


def _capture_document_id(instance: object) -> None:
    if type(instance).__name__ == "Document":
        instance.id = 42  # type: ignore[attr-defined]


class TestIngestDocuments:

    def test_404_when_dataset_not_found(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = None
        response = client.post(
            "/datasets/99/documents",
            files=[("files", ("doc.pdf", _minimal_valid_pdf(), "application/pdf"))],
        )
        assert response.status_code == 404

    def test_new_file_returns_200_and_created(
        self,
        client: TestClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("adam_api.routers.datasets.settings.pvc_mount_path", str(tmp_path))
        mock_db.get = AsyncMock(side_effect=_db_get_side_effect(dataset=_make_dataset()))
        mock_db.add = MagicMock(side_effect=_capture_document_id)
        new_file = MagicMock()
        new_file.id = 7
        new_file.file_path = "dires/cerfa/2026_01_15_1321/doc.pdf"
        mock_db.execute = AsyncMock(
            side_effect=[
                _exec_result(
                    scalar_one_or_none=None
                ),  # existing document (dataset+checksum) -> aucun
                _exec_result(scalar_one_or_none=None),  # File existant par checksum -> aucun
                _exec_result(scalar_one_or_none=new_file),  # INSERT ... RETURNING -> cree
            ]
        )

        response = client.post(
            "/datasets/1/documents",
            files=[("files", ("doc.pdf", _minimal_valid_pdf(), "application/pdf"))],
        )

        assert response.status_code == 200
        body = response.json()
        assert body["created"] == 1
        assert body["already_exists"] == 0
        assert body["rejected"] == 0
        assert body["results"][0]["file_name"] == "doc.pdf"
        assert body["results"][0]["status"] == "created"

    def test_pdf_hors_taille_cree_en_error(
        self,
        client: TestClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Dataset a 12 pages exigees et un PDF d'une page : document cree en ERROR."""
        monkeypatch.setattr("adam_api.routers.datasets.settings.pvc_mount_path", str(tmp_path))
        mock_db.get = AsyncMock(
            side_effect=_db_get_side_effect(dataset=_make_dataset(expected_page_count=12))
        )
        mock_db.add = MagicMock(side_effect=_capture_document_id)
        new_file = MagicMock()
        new_file.id = 7
        new_file.file_path = "dires/cerfa/2026_01_15_1321/doc.pdf"
        mock_db.execute = AsyncMock(
            side_effect=[
                _exec_result(scalar_one_or_none=None),
                _exec_result(scalar_one_or_none=None),
                _exec_result(scalar_one_or_none=new_file),
            ]
        )

        response = client.post(
            "/datasets/1/documents",
            files=[("files", ("doc.pdf", _minimal_valid_pdf(), "application/pdf"))],
        )

        assert response.status_code == 200
        body = response.json()
        assert body["created"] == 0
        assert body["in_error"] == 1
        assert body["results"][0]["status"] == "error"
        assert body["results"][0]["reason"] == "1 page(s) au lieu de 12"

    def test_duplicate_file_in_dataset_returns_already_exists(
        self,
        client: TestClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("adam_api.routers.datasets.settings.pvc_mount_path", str(tmp_path))
        mock_db.get = AsyncMock(side_effect=_db_get_side_effect(dataset=_make_dataset()))
        existing_doc = MagicMock()
        existing_doc.id = 10
        existing_doc.file_id = 3
        mock_db.execute = AsyncMock(
            side_effect=[
                _exec_result(
                    one_or_none=(existing_doc, "dires/cerfa/2026_01_01_0000/doc.pdf")
                ),  # deja lie dans ce dataset
            ]
        )

        response = client.post(
            "/datasets/1/documents",
            files=[("files", ("doc.pdf", _minimal_valid_pdf(), "application/pdf"))],
        )

        assert response.status_code == 200
        body = response.json()
        assert body["created"] == 0
        assert body["already_exists"] == 1
        assert body["results"][0]["status"] == "already_exists"
        assert body["results"][0]["document_id"] == 10

    def test_non_pdf_content_rejected(
        self,
        client: TestClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("adam_api.routers.datasets.settings.pvc_mount_path", str(tmp_path))
        mock_db.get = AsyncMock(side_effect=_db_get_side_effect(dataset=_make_dataset()))

        response = client.post(
            "/datasets/1/documents",
            files=[("files", ("fake.pdf", b"not a real pdf", "application/pdf"))],
        )

        assert response.status_code == 200
        body = response.json()
        assert body["created"] == 0
        assert body["rejected"] == 1
        assert body["results"][0]["status"] == "rejected"
        assert body["results"][0]["reason"] == "non-PDF"
        # aucun appel DB pour un fichier rejete avant meme la validation
        mock_db.execute.assert_not_awaited()

    def test_multiple_files_detailed_per_file(
        self,
        client: TestClient,
        mock_db: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr("adam_api.routers.datasets.settings.pvc_mount_path", str(tmp_path))
        mock_db.get = AsyncMock(side_effect=_db_get_side_effect(dataset=_make_dataset()))
        mock_db.add = MagicMock(side_effect=_capture_document_id)
        new_file = MagicMock()
        new_file.id = 7
        new_file.file_path = "dires/cerfa/2026_01_15_1321/doc.pdf"
        mock_db.execute = AsyncMock(
            side_effect=[
                _exec_result(scalar_one_or_none=None),  # existing doc check (fichier 1)
                _exec_result(scalar_one_or_none=None),  # File select (fichier 1)
                _exec_result(scalar_one_or_none=new_file),  # INSERT RETURNING (fichier 1)
            ]
        )

        response = client.post(
            "/datasets/1/documents",
            files=[
                ("files", ("valid.pdf", _minimal_valid_pdf(), "application/pdf")),
                ("files", ("invalid.pdf", b"garbage", "application/pdf")),
            ],
        )

        assert response.status_code == 200
        body = response.json()
        assert body["received"] == 2
        assert body["created"] == 1
        assert body["rejected"] == 1
        statuses = {r["file_name"]: r["status"] for r in body["results"]}
        assert statuses["valid.pdf"] == "created"
        assert statuses["invalid.pdf"] == "rejected"


# ---------------------------------------------------------------------------
# Cycle de vie du dataset
# ---------------------------------------------------------------------------


class TestCycleDeVie:
    """DRAFT -> ACTIVE -> ARCHIVED, et rien d'autre.

    Avant ces regles, la route acceptait n'importe quel statut de l'enumeration
    depuis n'importe quel etat : un dataset actif pouvait redevenir brouillon,
    ce qui deverrouillait son schema alors que des documents etaient deja
    annotes avec.
    """

    def _activable(self, mock_db: AsyncMock, status: str = "DRAFT", field_count: int = 3):
        dataset = _make_dataset(status=status)
        schema = MagicMock()
        schema.id = 1
        schema.name = "Schema CERFA"
        schema.locked = False
        dataset.schema_row = schema
        mock_db.get.side_effect = [dataset, schema]
        mock_db.execute.return_value.scalar_one.return_value = field_count
        return dataset

    def test_brouillon_vers_actif(self, client: TestClient, mock_db: AsyncMock) -> None:
        dataset = self._activable(mock_db)
        response = client.patch("/datasets/1/status?status=ACTIVE")
        assert response.status_code == 200
        assert dataset.status == "ACTIVE"

    def test_activation_verrouille_le_schema(self, client: TestClient, mock_db: AsyncMock) -> None:
        dataset = self._activable(mock_db)
        client.patch("/datasets/1/status?status=ACTIVE")
        assert dataset.schema_row.locked is True

    def test_activation_refusee_si_le_schema_n_a_aucun_champ(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        dataset = self._activable(mock_db, field_count=0)
        response = client.patch("/datasets/1/status?status=ACTIVE")
        assert response.status_code == 422
        assert dataset.status == "DRAFT"
        assert dataset.schema_row.locked is False

    def test_actif_ne_revient_pas_a_brouillon(self, client: TestClient, mock_db: AsyncMock) -> None:
        dataset = _make_dataset(status="ACTIVE")
        mock_db.get.return_value = dataset
        response = client.patch("/datasets/1/status?status=DRAFT")
        assert response.status_code == 409
        assert dataset.status == "ACTIVE"

    def test_archive_est_terminal(self, client: TestClient, mock_db: AsyncMock) -> None:
        dataset = _make_dataset(status="ARCHIVED")
        mock_db.get.return_value = dataset
        assert client.patch("/datasets/1/status?status=ACTIVE").status_code == 409
        assert dataset.status == "ARCHIVED"

    def test_brouillon_vers_archive(self, client: TestClient, mock_db: AsyncMock) -> None:
        dataset = _make_dataset(status="DRAFT")
        mock_db.get.return_value = dataset
        assert client.patch("/datasets/1/status?status=ARCHIVED").status_code == 200
        assert dataset.status == "ARCHIVED"

    def test_actif_vers_archive(self, client: TestClient, mock_db: AsyncMock) -> None:
        dataset = _make_dataset(status="ACTIVE")
        mock_db.get.return_value = dataset
        assert client.patch("/datasets/1/status?status=ARCHIVED").status_code == 200
        assert dataset.status == "ARCHIVED"

    def test_reposer_le_meme_statut_ne_leve_pas(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        # Un client qui rejoue sa requete ne doit pas recevoir un conflit pour
        # un etat deja atteint.
        dataset = _make_dataset(status="ACTIVE")
        mock_db.get.return_value = dataset
        assert client.patch("/datasets/1/status?status=ACTIVE").status_code == 200

    def test_statut_hors_enumeration(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_dataset(status="DRAFT")
        assert client.patch("/datasets/1/status?status=EN_COURS").status_code == 422

    def test_le_patch_general_applique_les_memes_regles(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        """PATCH /datasets/{id} ne doit pas contourner le cycle de vie.

        Le statut y etait pose par setattr : la transition refusee sur la route
        dediee passait par celle-ci.
        """
        dataset = _make_dataset(status="ACTIVE")
        mock_db.get.return_value = dataset
        response = client.patch("/datasets/1", json={"status": "DRAFT"})
        assert response.status_code == 409
        assert dataset.status == "ACTIVE"

    def test_le_patch_general_modifie_toujours_les_autres_champs(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        dataset = _make_dataset(status="DRAFT")
        mock_db.get.return_value = dataset
        response = client.patch("/datasets/1", json={"name": "Nouveau nom"})
        assert response.status_code == 200
        assert dataset.name == "Nouveau nom"


# ---------------------------------------------------------------------------
# DELETE /datasets/{dataset_id}/documents/{document_id}
# ---------------------------------------------------------------------------


def _make_document(id: int = 7, dataset_id: int = 1, status: str = "RECEIVED") -> MagicMock:
    doc = MagicMock(spec=Document)
    doc.id = id
    doc.dataset_id = dataset_id
    doc.status = status
    return doc


class TestRemoveDocument:
    @pytest.fixture(autouse=True)
    def _as_platform_admin(self, app: FastAPI) -> None:
        self._act_as(app)

    @staticmethod
    def _act_as(app: FastAPI, caller: Any = None) -> None:
        from adam_api.dependencies.auth import UserCaller, get_caller

        who = caller or UserCaller(
            matricule="MATADM", organisation_id=1, platform_role=PlatformRole.NOTA_ADMIN.value
        )
        app.dependency_overrides[get_caller] = lambda: who

    @staticmethod
    def _db_with(mock_db: AsyncMock, doc: Any, project_role: Optional[str] = None) -> None:
        dataset = _make_dataset(id=1, project_id=5)

        async def _get(model: Any, _id: int) -> Any:
            return {Dataset: dataset, Document: doc}.get(model)

        mock_db.get.side_effect = _get
        mock_db.scalar.return_value = project_role
        mock_db.execute.return_value.scalar_one.return_value = 0  # no submitted job

    def test_deletes_the_document_and_answers_204(self, client: TestClient, mock_db: AsyncMock) -> None:
        doc = _make_document()
        self._db_with(mock_db, doc)

        response = client.delete("/datasets/1/documents/7")

        assert response.status_code == 204
        assert response.content == b""
        mock_db.delete.assert_awaited_once_with(doc)

    def test_404_when_the_dataset_does_not_exist(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.side_effect = None
        mock_db.get.return_value = None

        assert client.delete("/datasets/1/documents/7").status_code == 404
        mock_db.delete.assert_not_called()

    def test_404_when_the_document_does_not_exist(self, client: TestClient, mock_db: AsyncMock) -> None:
        self._db_with(mock_db, None)

        assert client.delete("/datasets/1/documents/7").status_code == 404
        mock_db.delete.assert_not_called()

    def test_404_when_the_document_belongs_to_another_dataset(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        self._db_with(mock_db, _make_document(dataset_id=2))

        assert client.delete("/datasets/1/documents/7").status_code == 404
        mock_db.delete.assert_not_called()

    @pytest.mark.parametrize("status", ["RECEIVED", "INGESTED", "IN_PROGRESS", "PENDING_CONSENSUS", "VALIDATED", "ERROR"])
    def test_allowed_before_export(self, client: TestClient, mock_db: AsyncMock, status: str) -> None:
        self._db_with(mock_db, _make_document(status=status))

        assert client.delete("/datasets/1/documents/7").status_code == 204

    def test_409_when_a_job_was_already_submitted(self, client: TestClient, mock_db: AsyncMock) -> None:
        """Un job soumis est du travail rendu : on ne retire plus le document."""
        self._db_with(mock_db, _make_document(status="IN_PROGRESS"))
        mock_db.execute.return_value.scalar_one.return_value = 2

        response = client.delete("/datasets/1/documents/7")

        assert response.status_code == 409
        assert "2 job(s) soumis" in response.json()["detail"]
        mock_db.delete.assert_not_called()

    def test_unsubmitted_jobs_do_not_block_the_removal(self, client: TestClient, mock_db: AsyncMock) -> None:
        self._db_with(mock_db, _make_document(status="IN_PROGRESS"))
        mock_db.execute.return_value.scalar_one.return_value = 0

        assert client.delete("/datasets/1/documents/7").status_code == 204

    def test_409_for_an_exported_document(self, client: TestClient, mock_db: AsyncMock) -> None:
        self._db_with(mock_db, _make_document(status="EXPORTED"))

        response = client.delete("/datasets/1/documents/7")

        assert response.status_code == 409
        mock_db.delete.assert_not_called()


class TestRemoveDocumentAuthorization:
    """Seuls les administrateurs retirent un document."""

    @staticmethod
    def _call(app: FastAPI, client: TestClient, mock_db: AsyncMock, caller: Any, project_role: Any = None) -> Any:
        from adam_api.dependencies.auth import get_caller

        app.dependency_overrides[get_caller] = lambda: caller
        dataset, doc = _make_dataset(id=1, project_id=5), _make_document()

        async def _get(model: Any, _id: int) -> Any:
            return {Dataset: dataset, Document: doc}.get(model)

        mock_db.get.side_effect = _get
        mock_db.scalar.return_value = project_role
        mock_db.execute.return_value.scalar_one.return_value = 0  # no submitted job
        return client.delete("/datasets/1/documents/7")

    @pytest.mark.parametrize("platform_role", ["NOTA_ADMIN", "NOTA_SUPERVISOR"])
    def test_transverse_platform_roles_are_allowed(
        self, app: FastAPI, client: TestClient, mock_db: AsyncMock, platform_role: str
    ) -> None:
        from adam_api.dependencies.auth import UserCaller

        caller = UserCaller(matricule="M1", organisation_id=1, platform_role=platform_role)

        assert self._call(app, client, mock_db, caller).status_code == 204

    def test_business_admin_of_the_project_is_allowed(
        self, app: FastAPI, client: TestClient, mock_db: AsyncMock
    ) -> None:
        from adam_api.dependencies.auth import UserCaller

        caller = UserCaller(matricule="M1", organisation_id=1)

        response = self._call(app, client, mock_db, caller, project_role="BUSINESS_ADMIN")

        assert response.status_code == 204

    @pytest.mark.parametrize(
        "project_role", ["OPERATOR", None], ids=["operator-of-the-project", "no-role-on-this-project"]
    )
    def test_operator_or_member_of_nothing_here_is_refused(
        self, app: FastAPI, client: TestClient, mock_db: AsyncMock, project_role: Any
    ) -> None:
        """Pas de role sur CE projet : meme un BUSINESS_ADMIN d'un autre projet est refuse."""
        from adam_api.dependencies.auth import UserCaller

        caller = UserCaller(matricule="M1", organisation_id=1)

        response = self._call(app, client, mock_db, caller, project_role=project_role)

        assert response.status_code == 403
        mock_db.delete.assert_not_called()

    def test_nota_client_is_refused(self, app: FastAPI, client: TestClient, mock_db: AsyncMock) -> None:
        from adam_api.dependencies.auth import UserCaller

        caller = UserCaller(matricule="M1", organisation_id=1, platform_role="NOTA_CLIENT")

        assert self._call(app, client, mock_db, caller).status_code == 403

    def test_service_callers_are_refused(self, app: FastAPI, client: TestClient, mock_db: AsyncMock) -> None:
        from adam_api.dependencies.auth import ServiceCaller

        response = self._call(app, client, mock_db, ServiceCaller(service_name="internal-service"))

        assert response.status_code == 403
        mock_db.delete.assert_not_called()


def test_document_children_are_removed_by_the_database() -> None:
    """remove_document ne supprime que la ligne document : le reste repose sur ON DELETE CASCADE.

    Une base creee avec une regle RESTRICT (modele plus ancien) ferait echouer le retrait
    d'un document qui a des jobs : la regle du modele est donc verrouillee ici.
    """
    from adam_core.models import DocumentField, OcrResult

    for model in (Job, DocumentField, OcrResult):
        (fk,) = model.__table__.c.document_id.foreign_keys
        assert fk.ondelete == "CASCADE", model.__name__
