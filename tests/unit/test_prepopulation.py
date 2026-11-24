"""Tests unitaires du sous-module adam_worker/prepopulation/.

Trois niveaux, correspondant a la separation du sous-module :

    merger      fonction pure : fusion OCR + schema. Aucune base, aucun HTTP.
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
from sqlalchemy import update
from sqlalchemy.dialects import postgresql

from adam_api.exceptions.document_fields import FieldSpecMismatch
from adam_core.enums.status import DocumentFieldStatus, DocumentStatus
from adam_core.models import Document
from adam_worker.connectors.base import DocumentNonConforme, OcrConnectorError
from adam_worker.connectors.mock import MockOcrConnector
from adam_worker.prepopulation import poller as poller_module
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
    _permutation,
    default_pages_dir,
)

# Le seed stocke la cle complete dans field_key ; on couvre les deux conventions.
SPECS: List[Dict[str, Any]] = [
    {
        "page": 1,
        "id": 1,
        "section_id": "demandeur",
        "field_key": "demandeur.nom",
        "polygon": [1.0, 2.0, 3.0, 4.0],
        "group_id": None,
    },
    {
        "page": 1,
        "id": 2,
        "section_id": "demandeur",
        "field_key": "demandeur.prenom",
        "polygon": None,
        "group_id": None,
    },
    {
        "page": 1,
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
# poller : orchestration
# ---------------------------------------------------------------------------


class _FakeDb:
    """Rejoue candidats et contexte, et enregistre les UPDATE de statut.

    `candidates` : des ids (mode "ocr") ou des couples (id, mode). Comme la vraie
    requete, il ne rend que les documents `empty` quand elle porte le filtre
    `prealim_mode = ...`.
    """

    def __init__(self, candidates: List[Any], context: Optional[Any] = None) -> None:
        self.candidates = [c if isinstance(c, tuple) else (c, "ocr") for c in candidates]
        self.context = context
        self.statements: List[Any] = []

    async def execute(self, statement: Any) -> Any:
        self.statements.append(statement)
        outer = self
        filtre_empty = "prealim_mode =" in str(statement)

        class _Result:
            def all(self) -> Any:
                return [c for c in outer.candidates if not filtre_empty or c[1] == "empty"]

            def one_or_none(self) -> Any:
                return outer.context

        return _Result()


class _FakeApiClient:
    """Remplace les deux acces base du worker : lecture du schema, creation des champs."""

    #: Base de la session patchee : `persist` y ecrit le passage en IN_PROGRESS,
    #: comme la vraie transaction, pour que `_statuses` le retrouve.
    current_db: Optional["_FakeDb"] = None

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
        self.ocr_results: List[Any] = []

    async def load_schema(self, dataset_id: int, document_id: int) -> Dict[str, Any]:
        if self.specs_error:
            raise PrepopulationError("schema injoignable")
        return {"name": "schema de test", "pages": [], "field_specs": self.field_specs}

    async def persist(
        self, document_id: int, dataset_id: int, fields: List[Dict[str, Any]], ocr: Any
    ) -> Any:
        if self.bulk_error:
            raise PrepopulationError("creation des champs refusee : bulk refuse")
        self.bulk_payloads.append(list(fields))
        self.ocr_results.append(ocr)
        if _FakeApiClient.current_db is not None:
            _FakeApiClient.current_db.statements.append(
                update(Document)
                .where(Document.id == document_id)
                .values(status=DocumentStatus.IN_PROGRESS.value)
            )
        return SimpleNamespace(created=list(fields), skipped=[])


def _patch_session(monkeypatch: pytest.MonkeyPatch, db: _FakeDb) -> None:
    @asynccontextmanager
    async def _fake_get_async_session(**_kwargs: Any) -> AsyncIterator[_FakeDb]:
        yield db

    monkeypatch.setattr(poller_module, "get_async_session", _fake_get_async_session)
    _FakeApiClient.current_db = db


class _FakeStore:
    """Remplace settings_store : un dict en memoire, et la liste des ecritures."""

    OCR_STATUS_KEY = "ocr_status"

    def __init__(self) -> None:
        self.data: Dict[str, Any] = {}
        self.writes: List[Any] = []

    async def load(self, *_a: Any, **_k: Any) -> Dict[str, Any]:
        return dict(self.data)

    async def set_value(self, _db: Any, key: str, value: Any, updated_by: Any = None) -> None:
        self.writes.append((key, value))
        self.data[key] = value


@pytest.fixture(autouse=True)
def store(monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    fake = _FakeStore()
    monkeypatch.setattr(poller_module, "settings_store", fake)
    return fake


def _worker(api_client: Any, connector: Any = None, tmp_path: Optional[Path] = None) -> Any:
    worker = PrepopulationWorker(
        connector=connector or MockOcrConnector(["demandeur.nom"]),
        pvc_root=tmp_path or Path("/inexistant"),
    )
    worker._load_schema = api_client.load_schema  # type: ignore[method-assign]
    worker._persist = api_client.persist  # type: ignore[method-assign]
    return worker


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
        assert "'INGESTED'" in str(db.statements[0].compile(compile_kwargs={"literal_binds": True}))


class _MoteurHorsLigne(MockOcrConnector):
    """Connecteur dont la sonde echoue tant que `motif` est renseigne."""

    def __init__(self, motif: Optional[str]) -> None:
        super().__init__(["demandeur.nom"])
        self.motif = motif

    async def ping(self) -> Optional[str]:
        return self.motif


class TestMoteurHorsLigne:
    @pytest.mark.asyncio
    async def test_cycle_saute_sans_toucher_aux_documents(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        db = _FakeDb(candidates=[1, 2], context=SimpleNamespace(dataset_id=4, file_id=10, file_path="x.pdf"))
        _patch_session(monkeypatch, db)
        worker = _worker(_FakeApiClient(), connector=_MoteurHorsLigne("ConnectTimeout"))
        with caplog.at_level(logging.INFO):
            await worker.poll()
            await worker.poll()
        assert _statuses(db) == []  # aucun UPDATE : ni ERROR ni IN_PROGRESS
        alertes = [r for r in caplog.records if "injoignable" in r.getMessage()]
        assert len(alertes) == 1  # une alerte au changement d'etat, pas une par cycle
        assert "ConnectTimeout" in alertes[0].getMessage()

    @pytest.mark.asyncio
    async def test_reprise_au_retour_du_moteur(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10, file_path="x.pdf"))
        _patch_session(monkeypatch, db)
        moteur = _MoteurHorsLigne("ConnectError")
        worker = _worker(_FakeApiClient(), connector=moteur)
        with caplog.at_level(logging.INFO):
            await worker.poll()
            moteur.motif = None
            await worker.poll()
        assert DocumentStatus.IN_PROGRESS.value in _statuses(db)
        assert any("moteur OCR joignable" in r.getMessage() for r in caplog.records)


class TestPollerSucces:
    @pytest.mark.asyncio
    async def test_bilan_du_cycle_loggue(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),)
        _patch_session(monkeypatch, db)
        with caplog.at_level(logging.INFO):
            await _worker(_FakeApiClient()).poll()
        bilan = next(r.getMessage() for r in caplog.records if "cycle termine" in r.getMessage())
        assert f"documents=1 pre_alimentes=1 error=0 champs_crees={len(SPECS)}" in bilan

    @pytest.mark.asyncio
    async def test_document_passe_en_in_progress(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),)
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient()).poll()
        assert DocumentStatus.IN_PROGRESS.value in _statuses(db)

    @pytest.mark.asyncio
    async def test_tous_les_champs_du_schema_sont_envoyes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),)
        _patch_session(monkeypatch, db)
        api = _FakeApiClient()
        await _worker(api).poll()
        assert len(api.bulk_payloads[0]) == len(SPECS)

    @pytest.mark.asyncio
    async def test_ocr_indisponible_reste_un_succes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Un OCR muet n'est pas une erreur : champs vides, document utilisable."""
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),)
        _patch_session(monkeypatch, db)
        api = _FakeApiClient()
        await _worker(api, connector=MockOcrConnector(available=False)).poll()
        assert DocumentStatus.IN_PROGRESS.value in _statuses(db)
        assert all(p["ocr_value"] is None for p in api.bulk_payloads[0])


class TestPollerEchecs:
    @pytest.mark.asyncio
    async def test_connecteur_en_echec_met_en_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),)
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient(), connector=MockOcrConnector(failing=True)).poll()
        assert DocumentStatus.ERROR.value in _statuses(db)

    @pytest.mark.asyncio
    async def test_schema_injoignable_met_en_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),)
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient(specs_error=True)).poll()
        assert DocumentStatus.ERROR.value in _statuses(db)

    @pytest.mark.asyncio
    async def test_bulk_refuse_met_en_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),)
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient(bulk_error=True)).poll()
        assert DocumentStatus.ERROR.value in _statuses(db)

    @pytest.mark.asyncio
    async def test_schema_vide_met_en_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),)
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient(field_specs=[])).poll()
        assert DocumentStatus.ERROR.value in _statuses(db)

    @pytest.mark.asyncio
    async def test_une_erreur_n_interrompt_pas_le_lot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """CA : le document suivant doit etre traite malgre l'echec du precedent."""
        db = _FakeDb(candidates=[1, 2, 3], context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),)
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient(specs_error=True)).poll()
        assert _statuses(db).count(DocumentStatus.ERROR.value) == 3


class TestPollerConfidentialite:
    @pytest.mark.asyncio
    async def test_aucune_valeur_de_champ_dans_les_logs(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """CA : ni IBAN ni NIR ne doivent apparaitre, donc aucune valeur du tout."""
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),)
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
        db = _FakeDb(candidates=[1], context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),)
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


# ---------------------------------------------------------------------------
# poller : documents non conformes
# ---------------------------------------------------------------------------


class _ConnecteurFige:
    """Connecteur qui rend un document fixe, ou leve une exception fixe."""

    name = "fige"

    def __init__(self, rendu: Any = None, erreur: Optional[Exception] = None) -> None:
        self.rendu = rendu
        self.erreur = erreur

    async def ping(self) -> Optional[str]:
        return None

    async def extract(self, images: Any, modele: Any = None) -> Any:
        if self.erreur is not None:
            raise self.erreur
        return self.rendu


def _metadata_erreur(db: _FakeDb) -> Dict[str, Any]:
    """Motif ecrit par le dernier UPDATE, lu dans ses parametres compiles."""
    for statement in reversed(db.statements):
        if str(statement).startswith("UPDATE"):
            params = statement.compile().params
            for value in params.values():
                if isinstance(value, dict) and "erreur" in value:
                    return value["erreur"]
    raise AssertionError("aucun motif d'erreur ecrit")


class TestPollerNonConforme:
    @pytest.mark.asyncio
    async def test_aucune_page_reconnue_met_en_error_avec_motif(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _FakeDb(
            candidates=[1],
            context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),
        )
        _patch_session(monkeypatch, db)
        anomalies = [{"type": "pages_manquantes", "pages": [1, 2]}]
        connecteur = _ConnecteurFige(
            erreur=DocumentNonConforme("aucune page du formulaire reconnue", anomalies)
        )
        api = _FakeApiClient()
        await _worker(api, connector=connecteur).poll()

        assert DocumentStatus.ERROR.value in _statuses(db)
        erreur = _metadata_erreur(db)
        assert erreur["motif"] == "document_non_conforme"
        assert erreur["etape"] == "pre_alimentation"
        assert erreur["anomalies_pages"] == anomalies
        # Aucun champ cree pour un document qui n'est pas le formulaire.
        assert api.bulk_payloads == []

    @pytest.mark.asyncio
    async def test_pages_manquantes_mettent_en_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _FakeDb(
            candidates=[1],
            context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),
        )
        _patch_session(monkeypatch, db)
        ocr = await MockOcrConnector(["demandeur.nom"]).extract([])
        assert ocr is not None
        ocr.metadata["anomalies_pages"] = [{"type": "pages_manquantes", "pages": [6]}]
        api = _FakeApiClient()
        await _worker(api, connector=_ConnecteurFige(rendu=ocr)).poll()

        assert DocumentStatus.ERROR.value in _statuses(db)
        assert _metadata_erreur(db)["motif"] == "pages_manquantes"
        assert api.bulk_payloads == []

    @pytest.mark.asyncio
    async def test_page_deplacee_ne_bloque_pas(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Une page deplacee est remise en ordre par le connecteur : pas d'ERROR."""
        db = _FakeDb(
            candidates=[1],
            context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),
        )
        _patch_session(monkeypatch, db)
        ocr = await MockOcrConnector(["demandeur.nom"]).extract([])
        assert ocr is not None
        ocr.metadata["anomalies_pages"] = [
            {"type": "page_deplacee", "rang": 9, "page_reconnue": 10}
        ]
        await _worker(_FakeApiClient(), connector=_ConnecteurFige(rendu=ocr)).poll()
        assert DocumentStatus.IN_PROGRESS.value in _statuses(db)

    @pytest.mark.asyncio
    async def test_l_erreur_technique_ecrit_aussi_son_motif(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _FakeDb(
            candidates=[1],
            context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),
        )
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient(), connector=MockOcrConnector(failing=True)).poll()
        assert "connecteur OCR en echec" in _metadata_erreur(db)["message"]


# ---------------------------------------------------------------------------
# poller : remise en ordre des images de page
# ---------------------------------------------------------------------------


class TestPermutation:
    def test_pages_9_et_10_inversees(self) -> None:
        ordre = {str(p): p for p in range(1, 13)} | {"9": 10, "10": 9}
        assert _permutation(ordre, 12) == {9: 10, 10: 9}

    def test_document_dans_l_ordre_rien_a_deplacer(self) -> None:
        assert _permutation({str(p): p for p in range(1, 13)}, 12) == {}

    def test_page_non_reconnue_completee_par_le_rang_restant(self) -> None:
        """Page 12 blanche, non lue : elle prend le seul rang libre."""
        ordre = {"1": 2, "2": 1} | {str(p): p for p in range(3, 12)}
        assert _permutation(ordre, 12) == {2: 1, 1: 2}

    def test_ordre_incoherent_ne_deplace_rien(self) -> None:
        assert _permutation({"13": 1}, 12) == {}  # page hors bornes
        assert _permutation({"1": 2, "2": 2}, 12) == {}  # rang en double
        assert _permutation(None, 12) == {}  # connecteur sans ordre (mock)
        assert _permutation({"x": 1}, 12) == {}


class TestPollerRemiseEnOrdre:
    @staticmethod
    def _pages(tmp_path: Path, nombre: int) -> Path:
        dossier = tmp_path / default_pages_dir(10)
        dossier.mkdir(parents=True)
        for rang in range(1, nombre + 1):
            # Le contenu dit quelle image c'etait au scan.
            (dossier / f"{rang:04d}.png").write_text(f"scan-{rang}")
        return dossier

    @pytest.mark.asyncio
    async def test_images_renommees_dans_l_ordre_du_formulaire(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        dossier = self._pages(tmp_path, 3)
        db = _FakeDb(
            candidates=[1],
            context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),
        )
        _patch_session(monkeypatch, db)
        ocr = await MockOcrConnector(["demandeur.nom"]).extract([])
        assert ocr is not None
        # Scan : page 1, page 3, page 2.
        ocr.metadata["ordre_pages"] = {"1": 1, "3": 2, "2": 3}
        await _worker(
            _FakeApiClient(), connector=_ConnecteurFige(rendu=ocr), tmp_path=tmp_path
        ).poll()

        contenus = [(dossier / f"{n:04d}.png").read_text() for n in (1, 2, 3)]
        assert contenus == ["scan-1", "scan-3", "scan-2"]
        assert sorted(p.name for p in dossier.iterdir()) == ["0001.png", "0002.png", "0003.png"]
        assert DocumentStatus.IN_PROGRESS.value in _statuses(db)

    @pytest.mark.asyncio
    async def test_document_en_ordre_images_intactes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        dossier = self._pages(tmp_path, 3)
        db = _FakeDb(
            candidates=[1],
            context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),
        )
        _patch_session(monkeypatch, db)
        ocr = await MockOcrConnector(["demandeur.nom"]).extract([])
        assert ocr is not None
        ocr.metadata["ordre_pages"] = {"1": 1, "2": 2, "3": 3}
        await _worker(
            _FakeApiClient(), connector=_ConnecteurFige(rendu=ocr), tmp_path=tmp_path
        ).poll()

        contenus = [(dossier / f"{n:04d}.png").read_text() for n in (1, 2, 3)]
        assert contenus == ["scan-1", "scan-2", "scan-3"]


class TestMetadataJsonNull:
    @pytest.mark.asyncio
    async def test_la_fusion_ne_part_que_d_un_objet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Un document cree avec metadata_=None porte un JSON null, pas un NULL
        SQL. En JSONB, null || {...} rend [null, {...}], et GET /documents
        tombait en 500 sur ce tableau. La base de la fusion doit donc etre
        testee sur son type, pas seulement sur NULL."""
        db = _FakeDb(
            candidates=[1],
            context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),
        )
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient(), connector=MockOcrConnector(failing=True)).poll()

        update_sql = next(str(s) for s in reversed(db.statements) if str(s).startswith("UPDATE"))
        assert "jsonb_typeof(nota.document.metadata)" in update_sql
        assert "coalesce" not in update_sql.lower()


# ---------------------------------------------------------------------------
# poller : PDF regenere dans l'ordre du formulaire
# ---------------------------------------------------------------------------


def _pdf_textes(chemin: Path) -> List[str]:
    import pymupdf

    with pymupdf.open(str(chemin)) as doc:
        return [page.get_text().strip() for page in doc]


def _ecrire_pdf(chemin: Path, textes: List[str]) -> None:
    import pymupdf

    chemin.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    for texte in textes:
        doc.new_page().insert_text((72, 72), texte)
    doc.save(str(chemin))
    doc.close()


class TestReorderPdf:
    def test_pages_ecrites_dans_l_ordre_demande(self, tmp_path: Path) -> None:
        from adam_core.utils.pdf_render import reorder_pdf

        source = tmp_path / "scan.pdf"
        _ecrire_pdf(source, ["scan-1", "scan-2", "scan-3"])
        reorder_pdf(source, tmp_path / "ordonne.pdf", [1, 3, 2])
        assert _pdf_textes(tmp_path / "ordonne.pdf") == ["scan-1", "scan-3", "scan-2"]
        # L'original n'est pas touche.
        assert _pdf_textes(source) == ["scan-1", "scan-2", "scan-3"]

    def test_pdf_render_n_utilise_plus_l_alias_fitz(self) -> None:
        """PyMuPDF s'importe sous le nom pymupdf, comme cote nota : l'alias
        historique fitz y faisait lever « name 'fitz' is not defined »."""
        from adam_core.utils import pdf_render
        assert not hasattr(pdf_render, "fitz")
        assert hasattr(pdf_render, "pymupdf")



    def test_ordre_incompatible_ne_laisse_aucun_fichier(self, tmp_path: Path) -> None:
        from adam_core.utils.pdf_render import PdfRenderError, reorder_pdf

        source = tmp_path / "scan.pdf"
        _ecrire_pdf(source, ["scan-1", "scan-2"])
        with pytest.raises(PdfRenderError):
            reorder_pdf(source, tmp_path / "ordonne.pdf", [1, 3])
        assert sorted(p.name for p in tmp_path.iterdir()) == ["scan.pdf"]


class TestPollerPdfOrdonne:
    @pytest.mark.asyncio
    async def test_pdf_regenere_et_file_pointe_dessus(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _ecrire_pdf(tmp_path / "org/cerfa/doc.pdf", ["scan-1", "scan-2", "scan-3"])
        dossier = TestPollerRemiseEnOrdre._pages(tmp_path, 3)
        db = _FakeDb(
            candidates=[1],
            context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),
        )
        _patch_session(monkeypatch, db)
        ocr = await MockOcrConnector(["demandeur.nom"]).extract([])
        assert ocr is not None
        ocr.metadata["ordre_pages"] = {"1": 1, "3": 2, "2": 3}
        await _worker(
            _FakeApiClient(), connector=_ConnecteurFige(rendu=ocr), tmp_path=tmp_path
        ).poll()

        # PDF et images suivent le meme ordre, celui du formulaire.
        assert _pdf_textes(tmp_path / "org/cerfa/doc_ordonne.pdf") == [
            "scan-1",
            "scan-3",
            "scan-2",
        ]
        assert (dossier / "0002.png").read_text() == "scan-3"
        # L'original reste, trace du scan tel que recu.
        assert _pdf_textes(tmp_path / "org/cerfa/doc.pdf") == ["scan-1", "scan-2", "scan-3"]
        # Le FILE pointe sur la copie ordonnee.
        maj_file = [s.compile().params for s in db.statements if str(s).startswith("UPDATE nota.file")]
        assert maj_file and maj_file[0]["file_path"] == "org/cerfa/doc_ordonne.pdf"
        assert DocumentStatus.IN_PROGRESS.value in _statuses(db)

    @pytest.mark.asyncio
    async def test_pdf_absent_n_empeche_pas_les_images(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        dossier = TestPollerRemiseEnOrdre._pages(tmp_path, 3)
        db = _FakeDb(
            candidates=[1],
            context=SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf"),
        )
        _patch_session(monkeypatch, db)
        ocr = await MockOcrConnector(["demandeur.nom"]).extract([])
        assert ocr is not None
        ocr.metadata["ordre_pages"] = {"1": 1, "3": 2, "2": 3}
        await _worker(
            _FakeApiClient(), connector=_ConnecteurFige(rendu=ocr), tmp_path=tmp_path
        ).poll()

        assert (dossier / "0002.png").read_text() == "scan-3"
        assert not any(str(s).startswith("UPDATE file") for s in db.statements)
        assert DocumentStatus.IN_PROGRESS.value in _statuses(db)

# ---------------------------------------------------------------------------
# poller : modes de pre-alimentation, statut du moteur, ecriture
# ---------------------------------------------------------------------------

_CONTEXT = SimpleNamespace(dataset_id=4, file_id=10, file_path="org/cerfa/doc.pdf")


class _Espion(MockOcrConnector):
    """Compte les appels au moteur ; `motif` fait echouer la sonde."""

    def __init__(self, motif: Optional[str] = None) -> None:
        super().__init__(["demandeur.nom"])
        self.motif = motif
        self.pings = 0
        self.extracts = 0

    async def ping(self) -> Optional[str]:
        self.pings += 1
        return self.motif

    async def extract(self, images: Any, modele: Any = None) -> Any:
        self.extracts += 1
        return await super().extract(images, modele)


class TestPrealimMode:
    @pytest.mark.asyncio
    async def test_empty_cree_les_champs_sans_appeler_l_ocr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _FakeDb(candidates=[(1, "empty")], context=_CONTEXT)
        _patch_session(monkeypatch, db)
        api, moteur = _FakeApiClient(), _Espion()
        await _worker(api, connector=moteur).poll()
        assert moteur.extracts == 0
        assert api.ocr_results == [None]  # pas d'OCR_RESULT
        assert all(p["ocr_value"] is None for p in api.bulk_payloads[0])
        assert DocumentStatus.IN_PROGRESS.value in _statuses(db)

    @pytest.mark.asyncio
    async def test_empty_passe_meme_moteur_hors_ligne(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _FakeDb(candidates=[(1, "empty")], context=_CONTEXT)
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient(), connector=_Espion("ConnectTimeout")).poll()
        assert _statuses(db) == [DocumentStatus.IN_PROGRESS.value]

    @pytest.mark.asyncio
    async def test_ocr_attend_le_moteur_sans_erreur(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _FakeDb(candidates=[(1, "ocr")], context=_CONTEXT)
        _patch_session(monkeypatch, db)
        moteur = _Espion("ConnectTimeout")
        await _worker(_FakeApiClient(), connector=moteur).poll()
        assert moteur.extracts == 0
        assert _statuses(db) == []  # reste INGESTED : ni ERROR ni IN_PROGRESS

    @pytest.mark.asyncio
    async def test_lot_mixte_moteur_hors_ligne_ne_traite_que_les_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _FakeDb(candidates=[(1, "ocr"), (2, "empty"), (3, "ocr")], context=_CONTEXT)
        _patch_session(monkeypatch, db)
        api = _FakeApiClient()
        await _worker(api, connector=_Espion("ConnectError")).poll()
        assert len(api.bulk_payloads) == 1  # le seul document empty
        selection = next(s for s in db.statements if str(s).startswith("SELECT"))
        assert "empty" in selection.compile().params.values()  # filtre pose dans la requete

    @pytest.mark.asyncio
    async def test_lot_mixte_moteur_en_ligne_traite_tout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _FakeDb(candidates=[(1, "ocr"), (2, "empty")], context=_CONTEXT)
        _patch_session(monkeypatch, db)
        api, moteur = _FakeApiClient(), _Espion()
        await _worker(api, connector=moteur).poll()
        assert len(api.bulk_payloads) == 2
        assert moteur.extracts == 1  # seul le document ocr appelle le moteur
        assert api.ocr_results[0] is not None and api.ocr_results[1] is None

    @pytest.mark.asyncio
    async def test_ocr_desactive_en_base_met_les_ocr_en_attente_sans_ping(
        self, monkeypatch: pytest.MonkeyPatch, store: _FakeStore
    ) -> None:
        store.data["ocr_enabled"] = False
        db = _FakeDb(candidates=[(1, "ocr"), (2, "empty")], context=_CONTEXT)
        _patch_session(monkeypatch, db)
        api, moteur = _FakeApiClient(), _Espion()
        await _worker(api, connector=moteur).poll()
        assert moteur.pings == 0 and moteur.extracts == 0
        assert len(api.bulk_payloads) == 1  # l'empty passe, l'ocr attend
        assert store.writes == []  # pas de statut de joignabilite sans ping

    @pytest.mark.asyncio
    async def test_ocr_desactive_n_alerte_qu_une_fois(
        self, monkeypatch: pytest.MonkeyPatch, store: _FakeStore, caplog: pytest.LogCaptureFixture
    ) -> None:
        store.data["ocr_enabled"] = False
        _patch_session(monkeypatch, _FakeDb(candidates=[]))
        worker = _worker(_FakeApiClient())
        with caplog.at_level(logging.INFO):
            await worker.poll()
            await worker.poll()
        assert sum("OCR desactive" in r.getMessage() for r in caplog.records) == 1
        store.data["ocr_enabled"] = True
        with caplog.at_level(logging.INFO):
            await worker.poll()
        assert any("OCR reactive" in r.getMessage() for r in caplog.records)


class TestStatutMoteur:
    @pytest.mark.asyncio
    async def test_le_ping_est_ecrit_meme_sans_document(
        self, monkeypatch: pytest.MonkeyPatch, store: _FakeStore
    ) -> None:
        _patch_session(monkeypatch, _FakeDb(candidates=[]))
        await _worker(_FakeApiClient(), connector=_Espion("ConnectError")).poll()
        assert store.writes == [("ocr_status", {"reachable": False})]

    @pytest.mark.asyncio
    async def test_statut_reecrit_seulement_au_changement(
        self, monkeypatch: pytest.MonkeyPatch, store: _FakeStore
    ) -> None:
        _patch_session(monkeypatch, _FakeDb(candidates=[]))
        moteur = _Espion()
        worker = _worker(_FakeApiClient(), connector=moteur)
        await worker.poll()
        await worker.poll()
        assert store.writes == [("ocr_status", {"reachable": True})]  # une seule ecriture
        moteur.motif = "ConnectError"
        await worker.poll()
        assert store.writes[-1] == ("ocr_status", {"reachable": False})
        assert len(store.writes) == 2

    @pytest.mark.asyncio
    async def test_statut_non_enregistre_ne_bloque_pas_le_cycle(
        self, monkeypatch: pytest.MonkeyPatch, store: _FakeStore
    ) -> None:
        async def boom(*_a: Any, **_k: Any) -> None:
            raise RuntimeError("app_setting en lecture seule")

        monkeypatch.setattr(store, "set_value", boom)
        db = _FakeDb(candidates=[(1, "ocr")], context=_CONTEXT)
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient()).poll()
        assert DocumentStatus.IN_PROGRESS.value in _statuses(db)

    @pytest.mark.asyncio
    async def test_app_setting_illisible_garde_les_valeurs_par_defaut(
        self, monkeypatch: pytest.MonkeyPatch, store: _FakeStore
    ) -> None:
        async def boom(*_a: Any, **_k: Any) -> Dict[str, Any]:
            raise RuntimeError("base injoignable")

        monkeypatch.setattr(store, "load", boom)
        db = _FakeDb(candidates=[(1, "ocr")], context=_CONTEXT)
        _patch_session(monkeypatch, db)
        await _worker(_FakeApiClient()).poll()
        assert DocumentStatus.IN_PROGRESS.value in _statuses(db)


class _Session:
    """Session factice de la transaction d'ecriture : enregistre ce qu'elle execute."""

    def __init__(self) -> None:
        self.statements: List[Any] = []

    async def execute(self, statement: Any) -> Any:
        self.statements.append(statement)


def _sql(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


class TestEcritureEnUneTransaction:
    def _brancher(self, monkeypatch: pytest.MonkeyPatch, bulk: Any) -> _Session:
        session = _Session()

        @asynccontextmanager
        async def fake_session(**_k: Any) -> AsyncIterator[_Session]:
            yield session

        async def get_document(_db: Any, _id: int) -> Any:
            return SimpleNamespace(id=_id)

        monkeypatch.setattr(poller_module, "get_async_session", fake_session)
        monkeypatch.setattr(poller_module.document_fields, "get_document_or_none", get_document)
        monkeypatch.setattr(poller_module.document_fields, "create_bulk", bulk)
        return session

    @pytest.mark.asyncio
    async def test_champs_ocr_result_et_statut_dans_la_meme_session(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def bulk(_db: Any, _doc: Any, payloads: Any) -> Any:
            return SimpleNamespace(created=payloads, skipped=[])

        session = self._brancher(monkeypatch, bulk)
        worker = PrepopulationWorker(connector=_Espion(), pvc_root=Path("/inexistant"))
        ocr = await _ocr("demandeur.nom")
        await worker._persist(1, 4, [{"field_spec_id": 1}], ocr)
        sqls = [_sql(s) for s in session.statements]
        assert "ON CONFLICT ON CONSTRAINT uq_ocr_result_document_dataset DO UPDATE" in sqls[0]
        assert sqls[1].startswith("UPDATE") and "document" in sqls[1]

    @pytest.mark.asyncio
    async def test_sans_ocr_pas_d_ocr_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def bulk(_db: Any, _doc: Any, payloads: Any) -> Any:
            return SimpleNamespace(created=payloads, skipped=[])

        session = self._brancher(monkeypatch, bulk)
        worker = PrepopulationWorker(connector=_Espion(), pvc_root=Path("/inexistant"))
        await worker._persist(1, 4, [{"field_spec_id": 1}], None)
        assert len(session.statements) == 1 and _sql(session.statements[0]).startswith("UPDATE")

    @pytest.mark.asyncio
    async def test_ocr_result_porte_fournisseur_modele_et_json(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def bulk(_db: Any, _doc: Any, payloads: Any) -> Any:
            return SimpleNamespace(created=payloads, skipped=[])

        session = self._brancher(monkeypatch, bulk)
        connector = _Espion()
        connector.model = "mistral-ocr-2505"  # type: ignore[attr-defined]
        worker = PrepopulationWorker(connector=connector, pvc_root=Path("/inexistant"))
        await worker._persist(1, 4, [{"field_spec_id": 1}], await _ocr("demandeur.nom"))
        params = session.statements[0].compile(dialect=postgresql.dialect()).params
        assert params["provider"] == "MOCK"
        assert params["model"] == "mistral-ocr-2505"
        assert params["raw_json"]["smartdoc_version"] == "0.3"

    @pytest.mark.asyncio
    async def test_champs_refuses_n_ecrit_ni_ocr_result_ni_statut(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def bulk(*_a: Any) -> Any:
            raise FieldSpecMismatch([9], 1)

        session = self._brancher(monkeypatch, bulk)
        worker = PrepopulationWorker(connector=_Espion(), pvc_root=Path("/inexistant"))
        with pytest.raises(PrepopulationError):
            await worker._persist(1, 4, [{"field_spec_id": 9}], await _ocr("demandeur.nom"))
        assert session.statements == []
