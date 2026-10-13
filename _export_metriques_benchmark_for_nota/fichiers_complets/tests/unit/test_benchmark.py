"""Tests du worker de benchmark OCR (tests automatises en batch).

Sans base ni moteur : le comparateur et l'evaluation sont purs, le worker
tourne contre un faux depot et un faux connecteur, et les requetes du vrai
depot sont compilees pour PostgreSQL sans etre executees.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import pytest
from sqlalchemy.dialects import postgresql

from nota_core.enums.status import (
    ComparisonDiffKind,
    ComparisonVerdict,
    TestExecutionStatus,
)
from nota_core.schemas.interface_contract import (
    KVNumberValue,
    KVPair,
    KVTextValue,
    Page,
    Section,
    SmartdocDocument,
)
from nota_worker.benchmark import depot as depot_module
from nota_worker.benchmark.comparateur import (
    categorie,
    comparer,
    distance_edition,
    empreinte,
    normaliser,
)
from nota_worker.benchmark.depot import DepotBenchmark, ExecutionReservee
from nota_worker.benchmark.evaluation import Agregat, ChampVerite, evaluer_document
from nota_worker.benchmark.worker import TestExecutionWorker
from nota_worker.connectors.base import DocumentNonConforme, OcrConnectorError

CLE = "cle-de-test"


# -- Comparateur ----------------------------------------------------------------


class TestComparateur:
    def test_texte_normalise(self) -> None:
        assert comparer("Mme  THÉRY", "mme thery", "TEXT") is None

    def test_dates_et_nombres_par_valeur(self) -> None:
        assert comparer("17/09/1969", "1969-09-17", "DATE") is None
        assert comparer("17/09/69", "1969-09-17", "DATE") is None
        assert comparer("1 738,26", "1738.26", "NUMBER") is None
        assert comparer("true", "oui", "BOOLEAN") is None

    def test_missing_et_wrong(self) -> None:
        manque = comparer("DUPONT", None, "TEXT")
        assert manque is not None and manque.verdict == ComparisonVerdict.MISSING
        faux = comparer("DUPONT", "DURAND", "TEXT")
        assert faux is not None and faux.verdict == ComparisonVerdict.WRONG
        assert faux.edit_distance == 3

    def test_valeur_inventee_est_une_erreur(self) -> None:
        """Verite vide, moteur qui lit quelque chose : WRONG, pas silence."""
        ecart = comparer(None, "1947-01-01", "DATE")
        assert ecart is not None and ecart.verdict == ComparisonVerdict.WRONG
        assert comparer(None, "", "TEXT") is None

    def test_categories(self) -> None:
        assert categorie("FR76 3000", "FR76-3000") == ComparisonDiffKind.FORMAT
        assert categorie("524738039", "524738030") == ComparisonDiffKind.DIGIT
        assert categorie("DUPONT", "MARTIN") == ComparisonDiffKind.TOTAL

    def test_distance_et_empreinte(self) -> None:
        assert distance_edition("chat", "chats") == 1
        assert empreinte("FR76 3000", CLE) == empreinte("fr76  3000", CLE)
        assert empreinte("FR76 3000", CLE) != empreinte("FR76 3000", "autre-cle")
        assert empreinte(None, CLE) is None
        assert normaliser("  ", "TEXT") is None


# -- Evaluation d'un document ---------------------------------------------------------


def _champ(
    n: int,
    attendu: Optional[str],
    *,
    verifie: bool = True,
    sensible: bool = False,
    section: str = "deposant",
    cle: str = "nom",
    group_id: Optional[str] = None,
    value_type: str = "TEXT",
) -> ChampVerite:
    return ChampVerite(
        document_field_id=1000 + n,
        field_spec_id=n,
        section_id=section,
        field_key=cle,
        group_id=group_id,
        value_type=value_type,
        sensitive=sensible,
        attendu=attendu,
        verifie=verifie,
    )


def _ocr(*paires: KVPair) -> SmartdocDocument:
    return SmartdocDocument(
        smartdoc_version="0.3",
        document_id="bench",
        page_count=1,
        pages=[
            Page(
                page_number=1,
                width=1.0,
                height=1.0,
                sections=[Section(id="s", label="S", kv_pairs=list(paires))],
            )
        ],
        metadata={"provider": "test"},
    )


def _kv(id_: str, texte: str, group_id: Optional[str] = None) -> KVPair:
    return KVPair(id=id_, group_id=group_id, value=KVTextValue(text=texte))


class TestEvaluation:
    def test_seuls_les_champs_verifies_sont_juges(self) -> None:
        verite = [_champ(1, "DUPONT"), _champ(2, "Jean", verifie=False, cle="prenoms")]
        ocr = _ocr(_kv("deposant.nom", "DURAND"), _kv("deposant.prenoms", "Paul"))
        resultat = evaluer_document(verite, ocr, 9, CLE)
        assert resultat.fields_compared == 2
        assert resultat.fields_human_verified == 1
        assert [e["document_field_id"] for e in resultat.ecarts] == [1001]
        agregat = resultat.agregats[1]
        assert (agregat.field_key, agregat.compared, agregat.diff_count) == ("deposant.nom", 1, 1)
        # DUPONT lu DURAND : une substitution, comptee en faux positif ET negatif.
        assert (agregat.vp, agregat.fp, agregat.fn, agregat.substitutions) == (0, 1, 1, 1)

    def test_champ_sensible_rien_en_clair(self) -> None:
        verite = [_champ(1, "FR7630001", sensible=True, section="gestion_budget", cle="iban")]
        ecart = evaluer_document(
            verite, _ocr(_kv("gestion_budget.iban", "FR7630007")), 9, CLE
        ).ecarts[0]
        assert ecart["expected_value"] is None and ecart["observed_value"] is None
        assert ecart["observed_hmac"] == empreinte("FR7630007", CLE)
        assert ecart["diff_kind"] == "DIGIT"
        assert ecart["edit_distance"] == 1

    def test_lignes_de_tableau_jugees_chacune(self) -> None:
        """T7 : chaque pret compare a sa propre ligne de verite."""
        verite = [
            _champ(n, ref, section="credits_consommation", cle="reference", group_id=f"pret_{n}")
            for n, ref in ((1, "ADVANZIA"), (2, "DIAC"), (3, None))
        ]
        ocr = _ocr(
            _kv("credits_consommation.reference", "ADVANZIA", "pret_1"),
            _kv("credits_consommation.reference", "DIAX", "pret_2"),
        )
        resultat = evaluer_document(verite, ocr, 9, CLE)
        assert [(e["document_field_id"], e["verdict"]) for e in resultat.ecarts] == [
            (1002, "WRONG")
        ]
        assert resultat.agregats[2].field_key == "credits_consommation.reference[pret_2]"

    def test_histogramme_et_hors_schema(self) -> None:
        verite = [_champ(1, "DUPONT"), _champ(2, "12", cle="age", value_type="NUMBER")]
        ocr = _ocr(
            KVPair(id="deposant.nom", value=KVTextValue(text="DUPONT", confidence=0.95)),
            KVPair(id="deposant.age", value=KVNumberValue(value=13, confidence=0.951)),
            _kv("autre.champ", "X"),
        )
        resultat = evaluer_document(verite, ocr, 9, CLE)
        assert resultat.histogramme == {"TEXT": {"0.95": [1, 0]}, "NUMBER": {"0.95": [0, 1]}}
        assert resultat.unexpected_count == 1

    def test_moteur_sans_confiance_n_alimente_pas_l_histogramme(self) -> None:
        """Mistral : la confiance des KVPair est le 1.0 par defaut du contrat."""
        ocr = _ocr(_kv("deposant.nom", "DURAND"))
        ocr.metadata["confidence_fournie"] = False
        resultat = evaluer_document([_champ(1, "DUPONT")], ocr, 9, CLE)
        assert resultat.histogramme == {}
        assert resultat.ecarts[0]["ocr_confidence"] is None

    def test_moteur_muet_tout_verifie_est_missing(self) -> None:
        resultat = evaluer_document([_champ(1, "DUPONT"), _champ(2, None, cle="x")], None, 9, CLE)
        assert [e["verdict"] for e in resultat.ecarts] == ["MISSING"]


# -- Worker -----------------------------------------------------------------------------


class _FauxDepot:
    def __init__(self, execution: Optional[ExecutionReservee], verite: List[ChampVerite]) -> None:
        self.execution = execution
        self._verite = verite
        self.enregistrements: List[Dict[str, Any]] = []
        self.fin: Dict[str, Any] = {}
        self.reservations: List[Any] = []

    async def echouer_bloquees(self, delai: timedelta) -> int:
        return 0

    async def reserver_execution(self, provider: str, modele: Optional[str]) -> Any:
        self.reservations.append((provider, modele))
        execution, self.execution = self.execution, None
        return execution

    async def identifier(self, execution_id: int, version: str, empreinte: str) -> None:
        self.identite = (version, empreinte)

    async def schema(self, schema_id: int) -> Dict[str, Any]:
        return {
            "name": "Test",
            "pages": [],
            "field_specs": [
                {
                    "id": 1,
                    "page": 1,
                    "section_id": "deposant",
                    "field_key": "nom",
                    "value_type": "TEXT",
                }
            ],
        }

    async def documents(self, ids: List[int]) -> List[Any]:
        return [(i, 100 + i) for i in ids]

    async def verite(self, document_id: int) -> List[ChampVerite]:
        return self._verite

    async def enregistrer_document(self, execution_id: int, ecarts: Any, compteurs: Any) -> None:
        self.enregistrements.append({"ecarts": ecarts, "compteurs": compteurs})

    async def terminer(self, execution_id: int, statut: Any, **kwargs: Any) -> None:
        self.fin = {"statut": statut, **kwargs}


class _FauxConnecteur:
    name = "faux"
    model = "ocr-1"
    annotation_model = "annot-1"

    def __init__(self, reponses: List[Any]) -> None:
        self.reponses = reponses
        self.appels = 0

    async def extract(self, images: Any, modele: Any = None) -> Any:
        self.appels += 3
        reponse = self.reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse


def _execution(statut: str = "LOCKED", docs: Optional[List[int]] = None) -> ExecutionReservee:
    return ExecutionReservee(
        id=7, recipe_id=3, recipe_status=statut, document_ids=docs or [1, 2], schema_id=5
    )


def _worker(
    depot: _FauxDepot, connecteur: _FauxConnecteur, cle: str = CLE, sans_images: Any = ()
) -> TestExecutionWorker:
    worker = TestExecutionWorker(depot, connecteur, pvc_root=Path("/inexistant"), cle_hmac=cle)
    worker._images = lambda file_id: [] if file_id - 100 in sans_images else [Path("p.png")]
    return worker


class TestWorker:
    def test_execution_complete(self) -> None:
        depot = _FauxDepot(_execution(), [_champ(1, "DUPONT")])
        connecteur = _FauxConnecteur(
            [_ocr(_kv("deposant.nom", "DUPONT")), _ocr(_kv("deposant.nom", "DURAND"))]
        )
        asyncio.run(_worker(depot, connecteur).poll())

        assert depot.reservations == [("faux", "ocr-1 + annot-1")]
        assert [len(e["ecarts"]) for e in depot.enregistrements] == [0, 1]
        assert depot.enregistrements[1]["compteurs"]["ocr_calls_made"] == 3
        assert depot.fin["statut"] == TestExecutionStatus.COMPLETED
        assert depot.fin["agregats"][1].compared == 2
        assert depot.fin["agregats"][1].diff_count == 1
        assert depot.fin["message"] is None
        assert depot.identite[0] == "1" and len(depot.identite[1]) == 16

    def test_rien_en_attente(self) -> None:
        depot = _FauxDepot(None, [])
        asyncio.run(_worker(depot, _FauxConnecteur([])).poll())
        assert depot.fin == {}

    def test_recette_non_verrouillee(self) -> None:
        depot = _FauxDepot(_execution("DRAFT"), [])
        connecteur = _FauxConnecteur([])
        asyncio.run(_worker(depot, connecteur).poll())
        assert depot.fin["statut"] == TestExecutionStatus.FAILED
        assert "non verrouillee" in depot.fin["message"]
        assert connecteur.appels == 0

    def test_sans_cle_hmac(self) -> None:
        depot = _FauxDepot(_execution(), [])
        asyncio.run(_worker(depot, _FauxConnecteur([]), cle="").poll())
        assert depot.fin["statut"] == TestExecutionStatus.FAILED
        assert "COMPARISON_HMAC_KEY" in depot.fin["message"]

    def test_document_non_conforme_ne_stoppe_pas(self) -> None:
        depot = _FauxDepot(_execution(), [_champ(1, "DUPONT")])
        connecteur = _FauxConnecteur(
            [DocumentNonConforme("aucune page", []), _ocr(_kv("deposant.nom", "DUPONT"))]
        )
        asyncio.run(_worker(depot, connecteur).poll())
        assert depot.fin["statut"] == TestExecutionStatus.COMPLETED
        assert "[1]" in depot.fin["message"]
        assert depot.enregistrements[0]["ecarts"][0]["verdict"] == "MISSING"

    def test_moteur_injoignable_fait_echouer(self) -> None:
        depot = _FauxDepot(_execution(), [_champ(1, "DUPONT")])
        asyncio.run(_worker(depot, _FauxConnecteur([OcrConnectorError("injoignable")])).poll())
        assert depot.fin["statut"] == TestExecutionStatus.FAILED
        assert "document 1" in depot.fin["message"]


# -- Requetes du depot, compilees pour PostgreSQL --------------------------------------


class _SessionEnregistreuse:
    def __init__(self) -> None:
        self.instructions: List[Any] = []

    async def execute(self, instruction: Any) -> Any:
        self.instructions.append(instruction)
        return type("R", (), {"rowcount": 0})()


class TestDepotSql:
    @pytest.fixture
    def session(self, monkeypatch: pytest.MonkeyPatch) -> _SessionEnregistreuse:
        session = _SessionEnregistreuse()

        @asynccontextmanager
        async def faux(**_: Any) -> AsyncIterator[_SessionEnregistreuse]:
            yield session

        monkeypatch.setattr(depot_module, "get_async_session", faux)
        return session

    @staticmethod
    def _sql(instruction: Any) -> str:
        return str(instruction.compile(dialect=postgresql.dialect()))

    def test_enregistrer_document(self, session: _SessionEnregistreuse) -> None:
        ecart = {
            "execution_id": 7,
            "document_field_id": 1,
            "verdict": "WRONG",
            "diff_kind": "TOTAL",
            "ocr_confidence": None,
            "expected_value": "a",
            "observed_value": "b",
            "observed_hmac": None,
            "edit_distance": 1,
        }
        asyncio.run(
            DepotBenchmark().enregistrer_document(
                7, [ecart], {"documents_compared": 1, "diff_count": 1}
            )
        )
        insertion, maj = (self._sql(i) for i in session.instructions)
        assert (
            "ON CONFLICT ON CONSTRAINT uq_comparison_result_execution_field DO NOTHING" in insertion
        )
        assert "documents_compared=(test_execution.documents_compared +" in maj

    def test_terminer_ecrit_les_agregats(self, session: _SessionEnregistreuse) -> None:
        asyncio.run(
            DepotBenchmark().terminer(
                7,
                TestExecutionStatus.COMPLETED,
                histogramme={"TEXT": {}},
                agregats={1: Agregat("deposant.nom", 2, 1)},
            )
        )
        rapports, fin = (self._sql(i) for i in session.instructions)
        assert (
            "ON CONFLICT ON CONSTRAINT uq_evaluation_report_execution_field_spec DO UPDATE"
            in rapports
        )
        assert "UPDATE test_execution SET status=" in fin

    def test_echouer_bloquees(self, session: _SessionEnregistreuse) -> None:
        asyncio.run(DepotBenchmark().echouer_bloquees(timedelta(minutes=30)))
        sql = self._sql(session.instructions[0])
        assert "WHERE test_execution.status = " in sql and "test_execution.updated_at <" in sql


class TestDocumentSansImages:
    def test_ecarte_et_signale_sans_compter_contre_le_moteur(self) -> None:
        depot = _FauxDepot(_execution(docs=[1, 2]), [_champ(1, "DUPONT")])
        connecteur = _FauxConnecteur([_ocr(_kv("deposant.nom", "DUPONT"))])
        asyncio.run(_worker(depot, connecteur, sans_images=(1,)).poll())

        assert len(depot.enregistrements) == 1
        assert depot.fin["statut"] == TestExecutionStatus.COMPLETED
        assert "images de page absentes : [1]" in depot.fin["message"]
        assert depot.fin["agregats"][1].compared == 1


# -- Matrice de l'extraction -------------------------------------------------------


class TestMatrice:
    def test_les_cinq_cas(self) -> None:
        """vide/vide VN, vide/lu FP, rempli/vide FN, egal VP, different FP+FN."""
        cas = [
            (None, None, "vn"),
            (None, "INVENTE", "fp"),
            ("DUPONT", None, "fn"),
            ("Dupont", "DUPONT", "vp"),
        ]
        for attendu, lu, classe in cas:
            verite = [_champ(1, attendu)]
            ocr = _ocr(_kv("deposant.nom", lu)) if lu else None
            agregat = evaluer_document(verite, ocr, 9, CLE).agregats[1]
            comptes = {k: getattr(agregat, k) for k in ("vp", "fp", "fn", "vn")}
            assert comptes == {k: int(k == classe) for k in comptes}, (attendu, lu)
        agregat = evaluer_document(
            [_champ(1, "DUPONT")], _ocr(_kv("deposant.nom", "DURAND")), 9, CLE
        ).agregats[1]
        assert (agregat.fp, agregat.fn, agregat.substitutions) == (1, 1, 1)

    def test_taux_par_caractere(self) -> None:
        agregat = evaluer_document(
            [_champ(1, "DUPONT")], _ocr(_kv("deposant.nom", "DUPOND")), 9, CLE
        ).agregats[1]
        assert (agregat.somme_distance, agregat.somme_longueur_attendue) == (1, 6)

    def test_libelles_figes(self) -> None:
        champ = _champ(1, "x", sensible=True, value_type="TEXT")
        agregat = evaluer_document([champ], None, 9, CLE).agregats[1]
        assert (agregat.section_id, agregat.value_type, agregat.sensitive) == (
            "deposant",
            "TEXT",
            True,
        )


class TestEmpreinteSchema:
    def test_contenu_et_non_ids(self) -> None:
        from nota_worker.benchmark.worker import empreinte_schema

        base = {
            "pages": [{"page_number": 1, "description": "Deposant"}],
            "field_specs": [
                {"id": 1, "page": 1, "section_id": "d", "field_key": "nom", "value_type": "TEXT"}
            ],
        }
        autre_base = {
            "pages": base["pages"],
            "field_specs": [dict(base["field_specs"][0], id=999, polygon=[1.0] * 8)],
        }
        retype = {
            "pages": base["pages"],
            "field_specs": [dict(base["field_specs"][0], value_type="NUMBER")],
        }
        assert empreinte_schema(base) == empreinte_schema(autre_base)
        assert empreinte_schema(base) != empreinte_schema(retype)
