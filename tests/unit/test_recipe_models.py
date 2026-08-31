"""Modele de donnees des recettes de test OCR.

Ces tests compilent du SQL sans l'executer : ils verrouillent la forme du
schema — contraintes, chaines de filtrage, absence de fuite dans les repr —
pas son comportement contre une base. Le filtrage effectif est deja couvert
par test_org_scoping, qui itere tous les modeles scopes : les quatre tables
du domaine y entrent d'elles-memes en heritant des mixins.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from adam_core.db.scoping import _iter_scoped_models
from adam_core.models import (
    ComparisonResult,
    EvaluationReport,
    FieldSpec,
    TestExecution,
    TestRecipe,
)

TEST_ORG_ID = 42
MATRICULE = "MATTEST"

NEW_MODELS = (TestRecipe, TestExecution, ComparisonResult, EvaluationReport)


def _compile(statement: object) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]


class TestCouvertureScoping:
    def test_les_quatre_tables_sont_scopees(self) -> None:
        """Le domaine n'echappe pas au filtrage multi-tenant.

        Les roles NOTA transverses ouvrent des sessions non scopees et ne sont
        donc pas genes ; un NOTA_CLIENT, lui, reste enferme dans son
        organisation, et ces tables doivent l'y suivre.
        """
        scoped = set(_iter_scoped_models())
        for model in NEW_MODELS:
            assert model in scoped, f"{model.__name__} absent du filtrage"

    def test_chaine_organisation_remonte_jusqu_au_projet(self) -> None:
        for model in NEW_MODELS:
            sql = _compile(select(model).where(model.__organisation_filter__(TEST_ORG_ID)))
            assert "organisation_id" in sql, f"{model.__name__} : filtre sans organisation"

    def test_chaine_projet_remonte_jusqu_aux_adhesions(self) -> None:
        for model in NEW_MODELS:
            sql = _compile(select(model).where(model.__project_filter__(MATRICULE)))
            assert "user_project" in sql, f"{model.__name__} : filtre sans adhesion"


class TestContraintes:
    def test_un_seul_ecart_par_champ_et_par_execution(self) -> None:
        """La reprise d'un worker plante ne doit pas doubler les ecarts."""
        names = {c.name for c in ComparisonResult.__table__.constraints}
        assert "uq_comparison_result_execution_field" in names

    def test_un_seul_agregat_par_champ_et_par_execution(self) -> None:
        names = {c.name for c in EvaluationReport.__table__.constraints}
        assert "uq_evaluation_report_execution_field_spec" in names

    def test_nom_de_recette_unique_par_dataset(self) -> None:
        names = {c.name for c in TestRecipe.__table__.constraints}
        assert "uq_test_recipe_dataset_name" in names

    def test_id_des_ecarts_en_bigint(self) -> None:
        """Seule table du domaine en millions de lignes par an : le passage
        tardif int4 -> int8 serait une reecriture complete sous verrou."""
        assert "BIGINT" in str(ComparisonResult.__table__.c.id.type).upper()

    def test_created_at_non_nullable_sur_les_ecarts(self) -> None:
        """Ajoute plus tard, il daterait tout l'historique du jour de l'ALTER."""
        assert ComparisonResult.__table__.c.created_at.nullable is False

    def test_suppression_document_emporte_les_ecarts(self) -> None:
        """Droit a l'effacement : CASCADE, pas de procedure dediee a ecrire."""
        fk = next(iter(ComparisonResult.__table__.c.document_field_id.foreign_keys))
        assert fk.ondelete == "CASCADE"

    def test_l_agregat_ne_reference_aucun_document(self) -> None:
        """L'historique publie survit a la suppression d'un document."""
        assert "document_id" not in EvaluationReport.__table__.c
        assert "document_field_id" not in EvaluationReport.__table__.c

    def test_field_spec_porte_la_sensibilite(self) -> None:
        column = FieldSpec.__table__.c.is_sensitive
        assert column.nullable is False


class TestConfidentialite:
    def test_repr_ne_fuit_aucune_valeur(self) -> None:
        """expected/observed peuvent porter un IBAN : jamais dans un repr,
        donc jamais dans un logger.exception qui embarque l'objet."""
        row = ComparisonResult(
            id=1,
            execution_id=2,
            document_field_id=3,
            verdict="WRONG",
            diff_kind="DIGIT",
            expected_value="FR7612345678901234567890123",
            observed_value="FR7612345678901234567890124",
        )
        assert "FR76" not in repr(row)
