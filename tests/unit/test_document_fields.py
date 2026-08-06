"""Tests unitaires du module adam_api/modules/document_fields/.

Le service porte les regles, le routeur les traduit en codes HTTP. Les deux sont
testes ensemble ici, avec une session simulee : ce qui compte est le contrat
rendu a l'appelant, pas le chemin SQL.

Criteres d'acceptation couverts : validation du field_spec_id contre le schema
du document (422), conflit sur le triplet unique (409 en unitaire), idempotence
du lot (rejouable sans doublon ni exception), et defauts metier sur status et
resolved_by.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Set, Tuple
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.dependencies.auth import UserCaller
from adam_api.modules.document_fields import router
from adam_core.enums.status import DocumentFieldStatus

DOCUMENT_ID = 1
SCHEMA_ID = 9
VALID_SPEC_IDS = {11, 12, 13}


class _FakeDb:
    """Simule juste ce que le service interroge.

    Trois lectures : le schema_id du dataset, les field_spec du schema, les
    triplets deja poses. Elles sont distinguees par l'ordre d'appel, le service
    les faisant toujours dans cette sequence.
    """

    def __init__(
        self,
        *,
        document: Any = None,
        schema_id: Optional[int] = SCHEMA_ID,
        valid_spec_ids: Optional[Set[int]] = None,
        existing: Optional[Set[Tuple[int, Optional[str]]]] = None,
    ) -> None:
        self.document = document if document is not None else SimpleNamespace(
            id=DOCUMENT_ID, dataset_id=4
        )
        self.schema_id = schema_id
        self.valid_spec_ids = VALID_SPEC_IDS if valid_spec_ids is None else valid_spec_ids
        self.existing = existing or set()
        self.added: List[Any] = []
        self.deleted: List[Any] = []
        self._call = 0

    async def get(self, model: Any, pk: Any) -> Any:
        name = getattr(model, "__name__", "")
        if name == "Document":
            return self.document
        if name == "DocumentField":
            return self.field_by_id(pk)
        return None

    def field_by_id(self, pk: Any) -> Any:
        for row in self.added:
            if getattr(row, "id", None) == pk:
                return row
        return None

    async def execute(self, _statement: Any) -> Any:
        self._call += 1
        call = self._call
        outer = self

        class _Result:
            def scalar_one_or_none(self) -> Any:
                return outer.schema_id

            def scalars(self) -> Any:
                return SimpleNamespace(all=lambda: list(outer.valid_spec_ids))

            def all(self) -> List[Any]:
                return [
                    SimpleNamespace(field_spec_id=spec_id, group_id=group_id)
                    for spec_id, group_id in outer.existing
                ]

        _ = call
        return _Result()

    def add(self, row: Any) -> None:
        row.id = len(self.added) + 100
        row.consensus_reached = False
        self.added.append(row)

    async def flush(self) -> None:
        return None

    async def delete(self, row: Any) -> None:
        self.deleted.append(row)


@pytest.fixture
def app() -> FastAPI:
    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    return fastapi_app


def _client(app: FastAPI, db: _FakeDb) -> TestClient:
    from adam_api.dependencies.auth import get_caller
    from adam_api.dependencies.db import get_db

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_caller] = lambda: UserCaller(
        matricule="MATTEST", organisation_id=1
    )
    return TestClient(app, raise_server_exceptions=False)


def _payload(**overrides: Any) -> Dict[str, Any]:
    body = {"field_spec_id": 11, "ocr_value": "x", "resolved_value": "x"}
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# POST /documents/{id}/fields
# ---------------------------------------------------------------------------


class TestCreateOne:
    def test_201(self, app: FastAPI) -> None:
        db = _FakeDb()
        assert (
            _client(app, db).post(f"/documents/{DOCUMENT_ID}/fields", json=_payload()).status_code
            == 201
        )

    def test_404_si_document_inconnu(self, app: FastAPI) -> None:
        db = _FakeDb(document=None)
        db.document = None
        response = _client(app, db).post(f"/documents/{DOCUMENT_ID}/fields", json=_payload())
        assert response.status_code == 404

    def test_422_si_field_spec_hors_schema(self, app: FastAPI) -> None:
        db = _FakeDb()
        response = _client(app, db).post(
            f"/documents/{DOCUMENT_ID}/fields", json=_payload(field_spec_id=999)
        )
        assert response.status_code == 422

    def test_409_si_le_triplet_existe(self, app: FastAPI) -> None:
        db = _FakeDb(existing={(11, None)})
        response = _client(app, db).post(f"/documents/{DOCUMENT_ID}/fields", json=_payload())
        assert response.status_code == 409

    def test_group_id_distingue_deux_champs(self, app: FastAPI) -> None:
        # Meme field_spec, group_id different : ce n'est pas un doublon.
        db = _FakeDb(existing={(11, "g1")})
        response = _client(app, db).post(
            f"/documents/{DOCUMENT_ID}/fields", json=_payload(group_id="g2")
        )
        assert response.status_code == 201

    def test_statut_par_defaut_pending(self, app: FastAPI) -> None:
        db = _FakeDb()
        _client(app, db).post(f"/documents/{DOCUMENT_ID}/fields", json=_payload())
        assert db.added[0].status == DocumentFieldStatus.PENDING.value


class TestResolvedBy:
    def test_conserve_quand_une_valeur_existe(self, app: FastAPI) -> None:
        db = _FakeDb()
        _client(app, db).post(
            f"/documents/{DOCUMENT_ID}/fields",
            json=_payload(resolved_value="v", resolved_by="ocr_system"),
        )
        assert db.added[0].resolved_by == "ocr_system"

    def test_efface_quand_le_champ_est_vide(self, app: FastAPI) -> None:
        """CA : jamais de resolveur sur un champ sans valeur resolue."""
        db = _FakeDb()
        _client(app, db).post(
            f"/documents/{DOCUMENT_ID}/fields",
            json=_payload(ocr_value=None, resolved_value=None, resolved_by="ocr_system"),
        )
        assert db.added[0].resolved_by is None


# ---------------------------------------------------------------------------
# POST /documents/{id}/fields/bulk
# ---------------------------------------------------------------------------


def _bulk(*specs: int) -> Dict[str, Any]:
    return {"fields": [_payload(field_spec_id=spec_id) for spec_id in specs]}


class TestCreateBulk:
    def test_201_et_tout_est_cree(self, app: FastAPI) -> None:
        db = _FakeDb()
        response = _client(app, db).post(f"/documents/{DOCUMENT_ID}/fields/bulk", json=_bulk(11, 12))
        assert response.status_code == 201
        body = response.json()
        assert len(body["created"]) == 2
        assert body["skipped"] == []

    def test_idempotent_sur_un_second_appel(self, app: FastAPI) -> None:
        """CA : rejouer le meme lot ne cree pas de doublon et ne leve pas."""
        db = _FakeDb(existing={(11, None), (12, None)})
        response = _client(app, db).post(f"/documents/{DOCUMENT_ID}/fields/bulk", json=_bulk(11, 12))
        assert response.status_code == 201
        body = response.json()
        assert body["created"] == []
        assert len(body["skipped"]) == 2
        assert db.added == []

    def test_conflit_partiel_ne_fait_pas_echouer_le_lot(self, app: FastAPI) -> None:
        db = _FakeDb(existing={(11, None)})
        body = _client(app, db).post(
            f"/documents/{DOCUMENT_ID}/fields/bulk", json=_bulk(11, 12, 13)
        ).json()
        assert len(body["created"]) == 2
        assert body["skipped"] == [{"field_spec_id": 11, "group_id": None}]

    def test_doublon_interne_au_lot(self, app: FastAPI) -> None:
        db = _FakeDb()
        body = _client(app, db).post(
            f"/documents/{DOCUMENT_ID}/fields/bulk", json=_bulk(11, 11)
        ).json()
        assert len(body["created"]) == 1
        assert len(body["skipped"]) == 1

    def test_422_rejette_le_lot_entier(self, app: FastAPI) -> None:
        """Un lot incoherent ne doit pas laisser un document a moitie rempli."""
        db = _FakeDb()
        response = _client(app, db).post(
            f"/documents/{DOCUMENT_ID}/fields/bulk", json=_bulk(11, 999)
        )
        assert response.status_code == 422
        assert db.added == []

    def test_lot_vide(self, app: FastAPI) -> None:
        db = _FakeDb()
        response = _client(app, db).post(f"/documents/{DOCUMENT_ID}/fields/bulk", json={"fields": []})
        assert response.status_code == 201
        assert response.json()["created"] == []

    def test_404_si_document_inconnu(self, app: FastAPI) -> None:
        db = _FakeDb()
        db.document = None
        response = _client(app, db).post(f"/documents/{DOCUMENT_ID}/fields/bulk", json=_bulk(11))
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /documents/{id}/fields/{field_id}
# ---------------------------------------------------------------------------


class TestDelete:
    def test_204(self, app: FastAPI) -> None:
        db = _FakeDb()
        db.added.append(SimpleNamespace(id=100, document_id=DOCUMENT_ID))
        response = _client(app, db).delete(f"/documents/{DOCUMENT_ID}/fields/100")
        assert response.status_code == 204
        assert len(db.deleted) == 1

    def test_404_si_champ_inconnu(self, app: FastAPI) -> None:
        db = _FakeDb()
        assert _client(app, db).delete(f"/documents/{DOCUMENT_ID}/fields/999").status_code == 404

    def test_404_si_le_champ_appartient_a_un_autre_document(self, app: FastAPI) -> None:
        # Sans ce controle, on supprimerait le champ d'un document voisin.
        db = _FakeDb()
        db.added.append(SimpleNamespace(id=100, document_id=999))
        assert _client(app, db).delete(f"/documents/{DOCUMENT_ID}/fields/100").status_code == 404
        assert db.deleted == []


def test_les_routes_sont_exposees_par_l_app() -> None:
    """Le routeur doit etre branche dans main, sinon rien de tout ceci n'existe.

    On lit le schema OpenAPI et non app.routes : cette version de FastAPI garde
    les routeurs inclus sous forme d'objets _IncludedRouter sans mettre les
    chemins a plat.

    La comparaison se fait sur la fin du chemin, pas sur sa totalite : selon les
    projets, l'application monte ses routeurs a la racine ou sous un prefixe de
    version. Verifier le prefixe ici ferait echouer le test sur une convention
    de deploiement qui ne concerne pas ce module.
    """
    from adam_api.main import app as real_app

    paths = list(real_app.openapi()["paths"])

    def _exposed(suffix: str) -> bool:
        return any(path.endswith(suffix) for path in paths)

    assert _exposed("/documents/{document_id}/fields")
    assert _exposed("/documents/{document_id}/fields/bulk")

    schema = real_app.openapi()["paths"]
    field_path = next(p for p in paths if p.endswith("/documents/{document_id}/fields/{field_id}"))
    assert "delete" in schema[field_path]
