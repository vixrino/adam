"""Tests unitaires du sous-module adam_worker/prepopulation/.

Trois niveaux, correspondant a la separation du sous-module :

    merger      fonction pure : fusion OCR + schema. Aucune base, aucun HTTP.
    api_client  transport : reprises, entetes, erreurs non rejouables.
    poller      orchestration : selection, transitions de statut, isolation.

Les criteres d'acceptation couverts sont ceux de la spec : les trois cas de
fusion (champ detecte, champ non detecte, OCR indisponible), le positionnement
de resolved_by, l'absence de valeur de champ dans les logs, les transitions
IN_PROGRESS / ERROR, et le fait qu'une erreur n'interrompt pas le lot.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncIterator, Dict, List, Optional

import pytest

from adam_core.enums.status import DocumentFieldStatus, DocumentStatus
from adam_worker.connectors.base import OcrConnectorError
from adam_worker.connectors.mock import MockOcrConnector
from adam_worker.prepopulation import poller as poller_module
from adam_worker.prepopulation.api_client import ApiClient, ApiClientError
from adam_worker.prepopulation.merger import (
    OCR_RESOLVER,
    count_detected,
    index_ocr_pairs,
    merge,
    semantic_key,
)
from adam_worker.prepopulation.poller import (
    PrepopulationError,
    PrepopulationWorker,
    default_pages_dir,
)

# Le seed stocke la cle complete dans field_key ; on couvre les deux conventions.
SPECS: List[Dict[str, Any]] = [
    {
        "id": 1,
        "section_id": "demandeur",
        "field_key": "demandeur.nom",
        "polygon": [1.0, 2.0, 3.0, 4.0],
        "group_id": None,
    },
    {
        "id": 2,
        "section_id": "demandeur",
        "field_key": "demandeur.prenom",
        "polygon": None,
        "group_id": None,
    },
    {
        "id": 3,
        "section_id": "bien",
        "field_key": "bien.adresse",
        "polygon": [9.0, 9.0],
        "group_id": "bien-1",
    },
]


async def _ocr(*detected: str) -> Any:
    return await MockOcrConnector(list(detected)).extract([Path("p1.png")])


# ---------------------------------------------------------------------------
# merger : la regle metier
# ---------------------------------------------------------------------------


class TestSemanticKey:
    def test_prefixe_quand_la_section_manque(self) -> None:
        assert semantic_key("demandeur", "nom") == "demandeur.nom"

    def test_ne_double_pas_la_section_deja_presente(self) -> None:
        # Sans cette garde on produirait "demandeur.demandeur.nom" et aucun
        # champ ne serait jamais rapproche.
        assert semantic_key("demandeur", "demandeur.nom") == "demandeur.nom"

    def test_sans_section(self) -> None:
        assert semantic_key(None, "nom") == "nom"


class TestMergeChampDetecte:
    @pytest.mark.asyncio
    async def test_valeur_confiance_et_polygone_viennent_de_l_ocr(self) -> None:
        payloads = merge(SPECS, await _ocr("demandeur.nom"))
        first = payloads[0]
        assert first["ocr_value"] == "valeur-mock"
        assert first["resolved_value"] == "valeur-mock"
        assert first["ocr_confidence"] == 0.95
        assert first["ocr_polygon"] == [10.0, 10.0, 200.0, 10.0, 200.0, 40.0, 10.0, 40.0]

    @pytest.mark.asyncio
    async def test_resolved_by_est_pose(self) -> None:
        payloads = merge(SPECS, await _ocr("demandeur.nom"))
        assert payloads[0]["resolved_by"] == OCR_RESOLVER

    @pytest.mark.asyncio
    async def test_statut_initial_pending(self) -> None:
        payloads = merge(SPECS, await _ocr("demandeur.nom"))
        assert payloads[0]["status"] == DocumentFieldStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_group_id_du_schema_prime(self) -> None:
        payloads = merge(SPECS, await _ocr("bien.adresse"))
        assert payloads[2]["group_id"] == "bien-1"


class TestMergeChampNonDetecte:
    @pytest.mark.asyncio
    async def test_valeurs_nulles(self) -> None:
        payloads = merge(SPECS, await _ocr("demandeur.nom"))
        absent = payloads[1]  # demandeur.prenom, non detecte
        assert absent["ocr_value"] is None
        assert absent["resolved_value"] is None
        assert absent["ocr_confidence"] is None

    @pytest.mark.asyncio
    async def test_polygone_du_schema_en_repli(self) -> None:
        payloads = merge(SPECS, await _ocr("demandeur.prenom"))
        assert payloads[0]["ocr_polygon"] == [1.0, 2.0, 3.0, 4.0]

    @pytest.mark.asyncio
    async def test_pas_de_resolveur_sur_un_champ_vide(self) -> None:
        """CA : jamais de "ocr_system" sur un champ sans valeur."""
        payloads = merge(SPECS, await _ocr("demandeur.nom"))
        assert payloads[1]["resolved_by"] is None


class TestMergeOcrIndisponible:
    def test_tous_les_champs_sont_crees_vides(self) -> None:
        payloads = merge(SPECS, None)
        assert len(payloads) == len(SPECS)
        assert all(p["ocr_value"] is None for p in payloads)
        assert all(p["resolved_by"] is None for p in payloads)

    def test_les_polygones_du_schema_sont_conserves(self) -> None:
        payloads = merge(SPECS, None)
        assert payloads[0]["ocr_polygon"] == [1.0, 2.0, 3.0, 4.0]
        assert payloads[1]["ocr_polygon"] is None


class TestMergeInvariants:
    @pytest.mark.asyncio
    async def test_le_schema_commande_pas_l_ocr(self) -> None:
        # Une cle detectee hors schema ne doit creer aucun champ : le document
        # porte exactement ce que son schema declare.
        payloads = merge(SPECS, await _ocr("demandeur.nom", "inconnu.champ"))
        assert len(payloads) == len(SPECS)
        assert {p["field_spec_id"] for p in payloads} == {1, 2, 3}

    @pytest.mark.asyncio
    async def test_ordre_du_schema_preserve(self) -> None:
        payloads = merge(SPECS, await _ocr("bien.adresse"))
        assert [p["field_spec_id"] for p in payloads] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_index_garde_la_premiere_occurrence(self) -> None:
        ocr = await _ocr("demandeur.nom", "demandeur.nom")
        assert len(index_ocr_pairs(ocr)) == 1

    def test_index_vide_si_pas_d_ocr(self) -> None:
        assert index_ocr_pairs(None) == {}

    @pytest.mark.asyncio
    async def test_count_detected(self) -> None:
        payloads = merge(SPECS, await _ocr("demandeur.nom", "bien.adresse"))
        assert count_detected(payloads) == 2


# ---------------------------------------------------------------------------
# Connecteur mock
# ---------------------------------------------------------------------------


class TestMockConnector:
    @pytest.mark.asyncio
    async def test_indisponible_rend_none(self) -> None:
        assert await MockOcrConnector(available=False).extract([]) is None

    @pytest.mark.asyncio
    async def test_en_echec_leve(self) -> None:
        with pytest.raises(OcrConnectorError):
            await MockOcrConnector(failing=True).extract([])

    @pytest.mark.asyncio
    async def test_document_conforme_au_contrat(self) -> None:
        ocr = await _ocr("demandeur.nom")
        assert ocr is not None
        assert ocr.smartdoc_version == "0.3"
        assert [kv.id for _p, _s, kv in ocr.iter_kv_pairs()] == ["demandeur.nom"]


# ---------------------------------------------------------------------------
# api_client : transport
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, payload: Optional[Dict[str, Any]] = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.content = b"{}" if payload is not None else b""
        self.text = str(payload)

    def json(self) -> Dict[str, Any]:
        return self._payload


class _FakeHttpClient:
    """Rejoue une sequence de reponses et enregistre les appels."""

    def __init__(self, responses: List[Any]) -> None:
        self._responses = responses
        self.calls: List[Dict[str, Any]] = []

    async def request(
        self, method: str, url: str, json: Any = None, headers: Any = None
    ) -> _FakeResponse:
        self.calls.append({"method": method, "url": url, "json": json, "headers": headers})
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    async def aclose(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralise l'attente entre deux tentatives : les tests ne doivent pas dormir."""

    async def _sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("adam_worker.prepopulation.api_client.asyncio.sleep", _sleep)


class TestApiClient:
    @pytest.mark.asyncio
    async def test_appel_nominal(self) -> None:
        http = _FakeHttpClient([_FakeResponse(200, {"id": 7, "schema_id": 3})])
        client = ApiClient("http://api:8000", client=http)  # type: ignore[arg-type]
        assert await client.get_dataset(7) == {"id": 7, "schema_id": 3}
        assert http.calls[0]["url"] == "http://api:8000/datasets/7"

    @pytest.mark.asyncio
    async def test_pas_d_entete_sans_cle(self) -> None:
        http = _FakeHttpClient([_FakeResponse(200, {})])
        client = ApiClient("http://api:8000", client=http)  # type: ignore[arg-type]
        await client.get_dataset(1)
        assert http.calls[0]["headers"] == {}

    @pytest.mark.asyncio
    async def test_entete_injectee_quand_la_cle_existe(self) -> None:
        """Point d'injection prevu pour l'API key a venir."""
        http = _FakeHttpClient([_FakeResponse(200, {})])
        client = ApiClient("http://api:8000", api_key="secret", client=http)  # type: ignore[arg-type]
        await client.get_dataset(1)
        assert http.calls[0]["headers"] == {"X-Internal-Token": "secret"}

    @pytest.mark.asyncio
    async def test_5xx_rejoue_puis_abandonne(self) -> None:
        http = _FakeHttpClient([_FakeResponse(500), _FakeResponse(503), _FakeResponse(500)])
        client = ApiClient("http://api:8000", client=http)  # type: ignore[arg-type]
        with pytest.raises(ApiClientError):
            await client.get_dataset(1)
        assert len(http.calls) == 3

    @pytest.mark.asyncio
    async def test_5xx_puis_succes(self) -> None:
        http = _FakeHttpClient([_FakeResponse(500), _FakeResponse(200, {"ok": True})])
        client = ApiClient("http://api:8000", client=http)  # type: ignore[arg-type]
        assert await client.get_dataset(1) == {"ok": True}
        assert len(http.calls) == 2

    @pytest.mark.asyncio
    async def test_4xx_n_est_pas_rejoue(self) -> None:
        # Une demande invalide ne deviendra pas valide en la repetant.
        http = _FakeHttpClient([_FakeResponse(422, {"detail": "hors schema"})])
        client = ApiClient("http://api:8000", client=http)  # type: ignore[arg-type]
        with pytest.raises(ApiClientError):
            await client.get_dataset(1)
        assert len(http.calls) == 1

    @pytest.mark.asyncio
    async def test_get_field_specs_chaine_les_deux_appels(self) -> None:
        http = _FakeHttpClient(
            [
                _FakeResponse(200, {"id": 4, "schema_id": 9}),
                _FakeResponse(200, {"id": 9, "field_specs": [{"id": 1}]}),
            ]
        )
        client = ApiClient("http://api:8000", client=http)  # type: ignore[arg-type]
        assert await client.get_field_specs(4) == [{"id": 1}]
        assert http.calls[1]["url"] == "http://api:8000/schemas/9"

    @pytest.mark.asyncio
    async def test_dataset_sans_schema(self) -> None:
        http = _FakeHttpClient([_FakeResponse(200, {"id": 4})])
        client = ApiClient("http://api:8000", client=http)  # type: ignore[arg-type]
        with pytest.raises(ApiClientError):
            await client.get_field_specs(4)


# ---------------------------------------------------------------------------
# poller : orchestration
# ---------------------------------------------------------------------------


class _FakeDb:
    """Rejoue candidats et contexte, et enregistre les UPDATE de statut."""

    def __init__(self, candidates: List[int], context: Optional[Any] = None) -> None:
        self.candidates = candidates
        self.context = context
        self.statements: List[Any] = []

    async def execute(self, statement: Any) -> Any:
        self.statements.append(statement)
        outer = self

        class _Result:
            def scalars(self) -> Any:
                return SimpleNamespace(all=lambda: outer.candidates)

            def one_or_none(self) -> Any:
                return outer.context

        return _Result()


class _FakeApiClient:
    def __init__(
        self,
        field_specs: Optional[List[Dict[str, Any]]] = None,
        *,
        specs_error: bool = False,
        bulk_error: bool = False,
    ) -> None:
        self.field_specs = field_specs if field_specs is not None else SPECS
        self.specs_error = specs_error
        self.bulk_error = bulk_error
        self.bulk_payloads: List[List[Dict[str, Any]]] = []

    async def get_field_specs(self, dataset_id: int) -> List[Dict[str, Any]]:
        if self.specs_error:
            raise ApiClientError("schema injoignable")
        return self.field_specs

    async def create_fields_bulk(
        self, document_id: int, fields: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        if self.bulk_error:
            raise ApiClientError("bulk refuse")
        self.bulk_payloads.append(list(fields))
        return {"created": list(fields), "skipped": []}


def _patch_session(monkeypatch: pytest.MonkeyPatch, db: _FakeDb) -> None:
    @asynccontextmanager
    async def _fake_get_async_session(**_kwargs: Any) -> AsyncIterator[_FakeDb]:
        yield db

    monkeypatch.setattr(poller_module, "get_async_session", _fake_get_async_session)


def _worker(api_client: Any, connector: Any = None, tmp_path: Optional[Path] = None) -> Any:
    return PrepopulationWorker(
        connector=connector or MockOcrConnector(["demandeur.nom"]),
        api_client=api_client,
        pvc_root=tmp_path or Path("/inexistant"),
    )


def _statuses(db: _FakeDb) -> List[str]:
    """Statuts poses par les UPDATE, lus dans les statements compiles."""
    found = []
    for statement in db.statements:
        text = str(statement)
        if text.startswith("UPDATE"):
            found.append(statement.compile().params.get("status"))
    return found


class TestPollerSelection:
    @pytest.mark.asyncio
    async def test_cycle_vide(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _FakeDb(candidates=[])
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient()).poll()
        assert len(db.statements) == 1  # la selection seule

    @pytest.mark.asyncio
    async def test_filtre_sur_ingested(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _FakeDb(candidates=[])
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient()).poll()
        assert "'INGESTED'" in str(
            db.statements[0].compile(compile_kwargs={"literal_binds": True})
        )


class TestPollerSucces:
    @pytest.mark.asyncio
    async def test_document_passe_en_in_progress(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10))
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient()).poll()
        assert DocumentStatus.IN_PROGRESS.value in _statuses(db)

    @pytest.mark.asyncio
    async def test_tous_les_champs_du_schema_sont_envoyes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10))
        _patch_session(monkeypatch, db)
        api = _FakeApiClient()
        await _worker(api).poll()
        assert len(api.bulk_payloads[0]) == len(SPECS)

    @pytest.mark.asyncio
    async def test_ocr_indisponible_reste_un_succes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Un OCR muet n'est pas une erreur : champs vides, document utilisable."""
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10))
        _patch_session(monkeypatch, db)
        api = _FakeApiClient()
        await _worker(api, connector=MockOcrConnector(available=False)).poll()
        assert DocumentStatus.IN_PROGRESS.value in _statuses(db)
        assert all(p["ocr_value"] is None for p in api.bulk_payloads[0])


class TestPollerEchecs:
    @pytest.mark.asyncio
    async def test_connecteur_en_echec_met_en_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10))
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient(), connector=MockOcrConnector(failing=True)).poll()
        assert DocumentStatus.ERROR.value in _statuses(db)

    @pytest.mark.asyncio
    async def test_schema_injoignable_met_en_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10))
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient(specs_error=True)).poll()
        assert DocumentStatus.ERROR.value in _statuses(db)

    @pytest.mark.asyncio
    async def test_bulk_refuse_met_en_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10))
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient(bulk_error=True)).poll()
        assert DocumentStatus.ERROR.value in _statuses(db)

    @pytest.mark.asyncio
    async def test_schema_vide_met_en_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10))
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient(field_specs=[])).poll()
        assert DocumentStatus.ERROR.value in _statuses(db)

    @pytest.mark.asyncio
    async def test_une_erreur_n_interrompt_pas_le_lot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CA : le document suivant doit etre traite malgre l'echec du precedent."""
        db = _FakeDb(candidates=[1, 2, 3], context=SimpleNamespace(dataset_id=4, file_id=10))
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient(specs_error=True)).poll()
        assert _statuses(db).count(DocumentStatus.ERROR.value) == 3


class TestPollerConfidentialite:
    @pytest.mark.asyncio
    async def test_aucune_valeur_de_champ_dans_les_logs(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """CA : ni IBAN ni NIR ne doivent apparaitre, donc aucune valeur du tout."""
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10))
        _patch_session(monkeypatch, db)
        secret = "FR7630006000011234567890189"
        connector = MockOcrConnector(["demandeur.nom"], value=secret)
        with caplog.at_level(logging.DEBUG):
            await _worker(_FakeApiClient(), connector=connector).poll()
        assert secret not in caplog.text

    @pytest.mark.asyncio
    async def test_le_log_porte_les_comptages(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10))
        _patch_session(monkeypatch, db)
        with caplog.at_level(logging.INFO):
            await _worker(_FakeApiClient()).poll()
        assert "detectes=1" in caplog.text
        assert "document_id=1" in caplog.text


class TestPageImages:
    def test_repertoire_absent_rend_une_liste_vide(self) -> None:
        # Pas d'erreur : sans images, l'OCR ne detecte rien et l'operateur saisit.
        worker = _worker(_FakeApiClient(), tmp_path=Path("/inexistant"))
        assert worker._page_images(1) == []

    def test_les_png_sont_tries(self, tmp_path: Path) -> None:
        directory = tmp_path / default_pages_dir(1)
        directory.mkdir(parents=True)
        for name in ("page_2.png", "page_1.png"):
            (directory / name).touch()
        worker = _worker(_FakeApiClient(), tmp_path=tmp_path)
        assert [p.name for p in worker._page_images(1)] == ["page_1.png", "page_2.png"]


def test_prepopulation_error_est_exportee() -> None:
    assert issubclass(PrepopulationError, Exception)
