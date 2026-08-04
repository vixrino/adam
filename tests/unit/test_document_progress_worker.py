"""Tests unitaires adam_worker/document_progress_worker.py

Deux niveaux, correspondant a la separation du module :

    derive_stage         fonction pure, la seule regle metier, testee en table.
    DocumentProgressWorker  cablage : selection des candidats, forme du SQL,
                            valeurs preparees pour l'upsert.

Comme pour test_page_image_worker.py, aucune base : la session est remplacee et
les requetes sont inspectees apres compilation.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, AsyncIterator, List, Optional

import pytest

from adam_core.enums.status import DocumentStage
from adam_worker import document_progress_worker as worker_module
from adam_worker.document_progress_worker import DocumentProgressWorker, derive_stage


# ---------------------------------------------------------------------------
# derive_stage : la regle metier
# ---------------------------------------------------------------------------

_BASE = {
    "pdf_received": True,
    "pages_rendered": False,
    "ocr_available": False,
    "fields_total": 0,
    "fields_filled": 0,
    "jobs_submitted": 0,
    "jobs_required": 3,
}


def _stage(**overrides: Any) -> DocumentStage:
    return derive_stage(**{**_BASE, **overrides})


class TestDeriveStage:
    def test_document_juste_ingere(self) -> None:
        assert _stage() is DocumentStage.INGESTED

    def test_pages_rendues(self) -> None:
        assert _stage(pages_rendered=True) is DocumentStage.PAGES_RENDERED

    def test_ocr_disponible_prime_sur_les_pages(self) -> None:
        assert _stage(pages_rendered=True, ocr_available=True) is DocumentStage.OCR_AVAILABLE

    def test_champs_prealimentes(self) -> None:
        stage = _stage(pages_rendered=True, ocr_available=True, fields_total=10, fields_filled=4)
        assert stage is DocumentStage.FIELDS_PREFILLED

    def test_champs_attendus_mais_aucun_rempli_reste_a_l_ocr(self) -> None:
        # fields_total > 0 ne suffit pas : les lignes peuvent exister vides.
        stage = _stage(ocr_available=True, fields_total=10, fields_filled=0)
        assert stage is DocumentStage.OCR_AVAILABLE

    def test_annotation_des_le_premier_job_soumis(self) -> None:
        stage = _stage(fields_total=10, fields_filled=10, jobs_submitted=1, jobs_required=3)
        assert stage is DocumentStage.ANNOTATION

    def test_consensus_atteint(self) -> None:
        stage = _stage(fields_total=10, fields_filled=10, jobs_submitted=3, jobs_required=3)
        assert stage is DocumentStage.CONSENSUS_REACHED

    def test_consensus_si_depassement(self) -> None:
        stage = _stage(jobs_submitted=5, jobs_required=3)
        assert stage is DocumentStage.CONSENSUS_REACHED

    def test_required_operators_a_zero_n_annonce_pas_un_consensus(self) -> None:
        """Sans cette garde, 0 >= 0 est vrai et tout document frais serait valide."""
        assert _stage(jobs_submitted=0, jobs_required=0) is DocumentStage.INGESTED

    def test_required_operators_a_zero_avec_jobs_reste_en_annotation(self) -> None:
        stage = _stage(jobs_submitted=2, jobs_required=0)
        assert stage is DocumentStage.ANNOTATION

    def test_pdf_absent_reste_ingested(self) -> None:
        assert _stage(pdf_received=False) is DocumentStage.INGESTED

    @pytest.mark.parametrize("stage", list(DocumentStage))
    def test_toutes_les_etapes_sont_atteignables(self, stage: DocumentStage) -> None:
        """Aucune valeur de l'enumeration ne doit etre morte."""
        reachable = {
            DocumentStage.INGESTED: {},
            DocumentStage.PAGES_RENDERED: {"pages_rendered": True},
            DocumentStage.OCR_AVAILABLE: {"ocr_available": True},
            DocumentStage.FIELDS_PREFILLED: {"fields_total": 1, "fields_filled": 1},
            DocumentStage.ANNOTATION: {"jobs_submitted": 1},
            DocumentStage.CONSENSUS_REACHED: {"jobs_submitted": 3},
        }
        assert _stage(**reachable[stage]) is stage


# ---------------------------------------------------------------------------
# Cablage du worker
# ---------------------------------------------------------------------------


def _row(**overrides: Any) -> Any:
    values = {
        "document_id": 1,
        "pdf_received": True,
        "pages_rendered": True,
        "ocr_available": True,
        "fields_total": 10,
        "fields_filled": 7,
        "fields_validated": 2,
        "jobs_submitted": 1,
        "jobs_required": 3,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _FakeDb:
    """Capture les requetes executees et rejoue des resultats programmes."""

    def __init__(self, candidate_ids: List[int], rows: Optional[List[Any]] = None) -> None:
        self._candidate_ids = candidate_ids
        self._rows = rows or []
        self.statements: List[Any] = []

    async def execute(self, statement: Any) -> Any:
        """Les trois requetes du cycle : candidats, agregats, upsert.

        Chacune consomme un accesseur different du resultat, il n'y a donc pas
        besoin de distinguer les appels : scalars() sert aux candidats, all()
        aux agregats, et l'upsert ignore le retour.
        """
        self.statements.append(statement)
        outer = self

        class _Result:
            def scalars(self) -> Any:
                return SimpleNamespace(all=lambda: outer._candidate_ids)

            def all(self) -> List[Any]:
                return outer._rows

        return _Result()


def _patch_session(monkeypatch: pytest.MonkeyPatch, db: _FakeDb) -> None:
    @asynccontextmanager
    async def _fake_get_async_session(**_kwargs: Any) -> AsyncIterator[_FakeDb]:
        yield db

    monkeypatch.setattr(worker_module, "get_async_session", _fake_get_async_session)


def _sql(statement: Any) -> str:
    return str(statement.compile(compile_kwargs={"literal_binds": True}))


class TestCandidateSelection:
    @pytest.mark.asyncio
    async def test_requete_candidats_couvre_les_deux_cas(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _FakeDb(candidate_ids=[1, 2])
        _patch_session(monkeypatch, db)
        await DocumentProgressWorker(batch_size=50).poll()

        sql = _sql(db.statements[0])
        assert "LEFT OUTER JOIN document_progress" in sql
        # Sans progression, ou progression expiree.
        assert "document_progress.document_id IS NULL" in sql
        assert "document_progress.computed_at <" in sql
        assert "LIMIT 50" in sql

    @pytest.mark.asyncio
    async def test_cycle_vide_n_ecrit_rien(self, monkeypatch: pytest.MonkeyPatch) -> None:
        db = _FakeDb(candidate_ids=[])
        _patch_session(monkeypatch, db)
        await DocumentProgressWorker().poll()
        assert len(db.statements) == 1  # la selection seule, pas d'upsert


class TestProgressQuery:
    def test_les_comptages_sont_des_sous_requetes_correlees(self) -> None:
        # Des LEFT JOIN cumules multiplieraient document_field par job et
        # fausseraient les deux comptes.
        sql = _sql(DocumentProgressWorker()._progress_query([1, 2]))
        assert sql.count("SELECT count(*)") == 5
        assert "LEFT OUTER JOIN file" in sql
        assert "LEFT OUTER JOIN dataset" in sql

    def test_compte_les_champs_renseignes_par_ocr_ou_resolution(self) -> None:
        sql = _sql(DocumentProgressWorker()._progress_query([1]))
        assert "document_field.ocr_value IS NOT NULL" in sql
        assert "document_field.resolved_value IS NOT NULL" in sql

    def test_ne_compte_que_les_jobs_soumis(self) -> None:
        sql = _sql(DocumentProgressWorker()._progress_query([1]))
        assert "job.state = 'SUBMITTED'" in sql

    def test_jobs_required_tombe_a_zero_sans_dataset(self) -> None:
        sql = _sql(DocumentProgressWorker()._progress_query([1]))
        assert "coalesce(dataset.required_operators, 0)" in sql.lower()


class TestValuesPreparedForUpsert:
    def test_traduit_une_ligne_en_valeurs(self) -> None:
        values = DocumentProgressWorker()._to_values(_row())
        assert values["document_id"] == 1
        assert values["stage"] == DocumentStage.ANNOTATION.value
        assert values["fields_filled"] == 7
        assert values["jobs_required"] == 3

    def test_les_booleens_sont_normalises(self) -> None:
        # Le driver peut renvoyer None plutot que False sur un LEFT JOIN vide.
        values = DocumentProgressWorker()._to_values(_row(pdf_received=None, ocr_available=None))
        assert values["pdf_received"] is False
        assert values["ocr_available"] is False

    @pytest.mark.asyncio
    async def test_upsert_gere_le_conflit_sur_document_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _FakeDb(candidate_ids=[1], rows=[_row()])
        _patch_session(monkeypatch, db)
        await DocumentProgressWorker().poll()

        sql = _sql(db.statements[-1])
        assert "INSERT INTO document_progress" in sql
        assert "ON CONFLICT (document_id) DO UPDATE" in sql
        # computed_at est repousse a chaque recalcul, sinon la ligne reste
        # eternellement perimee et le worker la reprend a chaque cycle.
        assert "computed_at = now()" in sql.lower()

    @pytest.mark.asyncio
    async def test_document_id_n_est_pas_reecrit_par_l_upsert(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        db = _FakeDb(candidate_ids=[1], rows=[_row()])
        _patch_session(monkeypatch, db)
        await DocumentProgressWorker().poll()

        set_clause = _sql(db.statements[-1]).split("DO UPDATE SET")[1]
        assert "document_id =" not in set_clause


class TestUpsertGuards:
    @pytest.mark.asyncio
    async def test_aucune_ligne_calculee_n_ecrit_rien(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Candidats trouves mais agregats vides : les documents ont disparu
        # entre les deux requetes. L'upsert doit etre saute, pg_insert().values([])
        # etant invalide.
        db = _FakeDb(candidate_ids=[1], rows=[])
        _patch_session(monkeypatch, db)
        await DocumentProgressWorker().poll()
        assert len(db.statements) == 2  # selection + agregats, pas d'upsert


class TestScoping:
    """document_progress derive d'un document : les deux filtres doivent porter."""

    def test_la_table_est_scopee(self) -> None:
        from adam_core.db.scoping import (
            OrganisationScoped,
            ProjectScoped,
            _iter_project_scoped_models,
            _iter_scoped_models,
        )
        from adam_core.models import DocumentProgress

        assert issubclass(DocumentProgress, OrganisationScoped)
        assert issubclass(DocumentProgress, ProjectScoped)
        assert DocumentProgress in set(_iter_scoped_models())
        assert DocumentProgress in set(_iter_project_scoped_models())

    def test_les_criteres_remontent_jusqu_au_projet(self) -> None:
        from sqlalchemy import select

        from adam_core.models import DocumentProgress

        org = _sql(select(DocumentProgress).where(DocumentProgress.__organisation_filter__(42)))
        assert "document_progress.document_id IN" in org
        assert "project.organisation_id = 42" in org

        proj = _sql(select(DocumentProgress).where(DocumentProgress.__project_filter__("MAT1")))
        assert "document_progress.document_id IN" in proj
        assert "\"user\".matricule = 'MAT1'" in proj


class TestCompletionRatio:
    def test_ratio_none_si_aucun_champ_attendu(self) -> None:
        from adam_core.models import DocumentProgress

        progress = DocumentProgress(document_id=1, stage=DocumentStage.INGESTED.value)
        progress.fields_total = 0
        progress.fields_filled = 0
        assert progress.fields_completion is None

    def test_ratio_calcule(self) -> None:
        from adam_core.models import DocumentProgress

        progress = DocumentProgress(document_id=1, stage=DocumentStage.ANNOTATION.value)
        progress.fields_total = 8
        progress.fields_filled = 2
        assert progress.fields_completion == 0.25


def test_le_worker_est_enregistre_dans_main() -> None:
    import inspect

    from adam_worker import main

    assert "DocumentProgressWorker()" in inspect.getsource(main._main)
