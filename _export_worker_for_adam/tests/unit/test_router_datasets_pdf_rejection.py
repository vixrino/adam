"""Test autonome : rejet des fichiers non-PDF a l'ingestion.

A deposer tel quel dans tests/unit/ de nota. Ne depend d'aucun helper du
test_router_datasets.py existant : il cree ses propres fixtures et son
propre dataset/schema/projet/organisation mockes. Teste uniquement que
POST /datasets/{id}/documents rejette un contenu qui n'est pas un PDF,
sans creer de Document ni toucher la base.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nota_api.routers.datasets import router


@pytest.fixture
def app() -> FastAPI:
    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    return fastapi_app


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    # dataset -> schema -> project -> organisation, resolus par db.get(Model, id).
    # On dispatche sur le nom de la classe pour ne dependre d'aucun import de modele.
    dataset = MagicMock()
    dataset.schema_id = 1
    dataset.project_id = 1
    schema = MagicMock()
    schema.document_type = "cerfa"
    project = MagicMock()
    project.organisation_id = 1
    organisation = MagicMock()
    organisation.slug = "dires"

    by_model = {
        "Dataset": dataset,
        "DocSchema": schema,
        "Project": project,
        "Organisation": organisation,
    }

    async def _get(model, _id):
        return by_model.get(getattr(model, "__name__", None))

    db.get = AsyncMock(side_effect=_get)
    return db


@pytest.fixture
def client(app: FastAPI, mock_db: AsyncMock) -> TestClient:
    from nota_api.dependencies.db import get_db

    app.dependency_overrides[get_db] = lambda: mock_db
    return TestClient(app, raise_server_exceptions=False)


class TestIngestRejectsNonPdf:
    def test_non_pdf_content_rejected(
        self, client: TestClient, mock_db: AsyncMock, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setattr(
            "nota_api.routers.datasets.settings.pvc_mount_path", str(tmp_path)
        )

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
        # un fichier rejete ne doit declencher aucune requete SQL
        mock_db.execute.assert_not_awaited()
