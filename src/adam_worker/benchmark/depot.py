"""Acces base du worker de benchmark : lectures du perimetre, ecritures du run.

Toutes les requetes du worker sont ici, et nulle part ailleurs : le worker
s'ecrit et se teste contre un faux depot en memoire, et ce module se relit
seul. Les seules tables ecrites sont test_execution, comparison_result et
evaluation_report : un benchmark ne touche jamais la donnee qu'il mesure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import exists, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from adam_core.db.session import get_async_session
from adam_core.enums.status import TestExecutionStatus
from adam_core.models import (
    ComparisonResult,
    Dataset,
    DocSchema,
    Document,
    DocumentField,
    EvaluationReport,
    FieldProposal,
    FieldSpec,
    SchemaPage,
    TestExecution,
    TestRecipe,
)
from adam_worker.benchmark.evaluation import Agregat, ChampVerite


@dataclass(frozen=True)
class ExecutionReservee:
    id: int
    recipe_id: int
    recipe_status: str
    document_ids: List[int]
    schema_id: int


class DepotBenchmark:
    """Lectures et ecritures du worker de benchmark, en base directe."""

    async def echouer_bloquees(self, delai: timedelta) -> int:
        """Passe en FAILED les executions RUNNING sans signe de vie depuis `delai`.

        Un worker arrete en plein run laisse son execution RUNNING pour toujours.
        Les champs corrects n'ecrivant aucune ligne, on ne sait pas reprendre ou
        il s'etait arrete : l'execution echoue, et une nouvelle la remplace.
        """
        limite = datetime.now(timezone.utc) - delai
        async with get_async_session() as db:
            resultat = await db.execute(
                update(TestExecution)
                .where(TestExecution.status == TestExecutionStatus.RUNNING.value)
                .where(TestExecution.updated_at < limite)
                .values(
                    status=TestExecutionStatus.FAILED.value,
                    finished_at=datetime.now(timezone.utc),
                    error_message="interrompue : aucun progres enregistre, a relancer",
                )
            )
            return int(getattr(resultat, "rowcount", 0) or 0)

    async def reserver_execution(
        self, ocr_provider: str, ocr_model_id: Optional[str]
    ) -> Optional[ExecutionReservee]:
        """Prend la plus ancienne execution PENDING et la passe en RUNNING.

        FOR UPDATE SKIP LOCKED : deux workers ne prennent jamais la meme. Le
        moteur est recopie sur l'execution au lancement : la configuration du
        dataset peut changer apres.
        """
        async with get_async_session() as db:
            execution = (
                await db.execute(
                    select(TestExecution)
                    .where(TestExecution.status == TestExecutionStatus.PENDING.value)
                    .order_by(TestExecution.created_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if execution is None:
                return None
            ligne = (
                await db.execute(
                    select(TestRecipe.status, TestRecipe.document_ids, Dataset.schema_id)
                    .join(Dataset, Dataset.id == TestRecipe.dataset_id)
                    .where(TestRecipe.id == execution.recipe_id)
                )
            ).one()
            execution.status = TestExecutionStatus.RUNNING.value
            execution.started_at = datetime.now(timezone.utc)
            execution.ocr_provider = ocr_provider
            execution.ocr_model_id = ocr_model_id
            await db.flush()
            return ExecutionReservee(
                id=execution.id,
                recipe_id=execution.recipe_id,
                recipe_status=str(ligne.status),
                document_ids=list(ligne.document_ids or []),
                schema_id=int(ligne.schema_id),
            )

    async def schema(self, schema_id: int) -> Dict[str, Any]:
        """Le schema sous la forme de GET /schemas/{id}, pour ModeleDocument."""
        async with get_async_session() as db:
            nom = (
                await db.execute(select(DocSchema.name).where(DocSchema.id == schema_id))
            ).scalar_one()
            pages = (
                await db.execute(
                    select(SchemaPage.page_number, SchemaPage.description)
                    .where(SchemaPage.schema_id == schema_id)
                    .order_by(SchemaPage.page_number)
                )
            ).all()
            specs = (
                (
                    await db.execute(
                        select(FieldSpec)
                        .where(FieldSpec.schema_id == schema_id)
                        .order_by(FieldSpec.page, FieldSpec.display_order, FieldSpec.id)
                    )
                )
                .scalars()
                .all()
            )
        return {
            "name": nom,
            "pages": [{"page_number": n, "description": d} for n, d in pages],
            "field_specs": [
                {
                    "id": fs.id,
                    "page": fs.page,
                    "section_id": fs.section_id,
                    "field_key": fs.field_key,
                    "group_id": fs.group_id,
                    "display_label": fs.display_label,
                    "description": fs.description,
                    "value_type": fs.value_type,
                    "polygon": fs.polygon,
                }
                for fs in specs
            ],
        }

    async def documents(self, document_ids: List[int]) -> List[Tuple[int, int]]:
        """(document_id, file_id) des documents de la recette, dans son ordre."""
        async with get_async_session() as db:
            lignes = (
                await db.execute(
                    select(Document.id, Document.file_id).where(Document.id.in_(document_ids))
                )
            ).all()
        par_id = {int(d): int(f) for d, f in lignes}
        return [(d, par_id[d]) for d in document_ids if d in par_id]

    async def verite(self, document_id: int) -> List[ChampVerite]:
        """Les document_field du document, dans l'ordre du schema (lignes de
        tableau comprises : pret_1 avant pret_2, ce que le merger suppose)."""
        verifie = exists().where(FieldProposal.document_field_id == DocumentField.id)
        async with get_async_session() as db:
            lignes = (
                await db.execute(
                    select(DocumentField, FieldSpec, verifie.label("verifie"))
                    .join(FieldSpec, FieldSpec.id == DocumentField.field_spec_id)
                    .where(DocumentField.document_id == document_id)
                    .order_by(FieldSpec.page, FieldSpec.display_order, FieldSpec.id)
                )
            ).all()
        return [
            ChampVerite(
                document_field_id=df.id,
                field_spec_id=fs.id,
                section_id=fs.section_id,
                field_key=fs.field_key,
                group_id=df.group_id,
                value_type=fs.value_type,
                sensitive=bool(fs.sensitive),
                attendu=df.resolved_value,
                verifie=bool(est_verifie),
            )
            for df, fs, est_verifie in lignes
        ]

    async def enregistrer_document(
        self, execution_id: int, ecarts: List[Dict[str, Any]], compteurs: Dict[str, int]
    ) -> None:
        """Ecrit les ecarts d'un document et fait avancer les totaux.

        Un document a la fois, dans sa propre transaction : la progression est
        visible pendant le run, et updated_at sert de signe de vie.
        """
        async with get_async_session() as db:
            if ecarts:
                await db.execute(
                    pg_insert(ComparisonResult)
                    .values(ecarts)
                    .on_conflict_do_nothing(constraint="uq_comparison_result_execution_field")
                )
            await db.execute(
                update(TestExecution)
                .where(TestExecution.id == execution_id)
                .values(
                    {
                        getattr(TestExecution, nom): getattr(TestExecution, nom) + valeur
                        for nom, valeur in compteurs.items()
                    }
                )
            )

    async def terminer(
        self,
        execution_id: int,
        statut: TestExecutionStatus,
        *,
        histogramme: Optional[Dict[str, Any]] = None,
        agregats: Optional[Dict[int, Agregat]] = None,
        message: Optional[str] = None,
    ) -> None:
        """Clot l'execution, et ecrit ses agregats par champ s'il y en a."""
        async with get_async_session() as db:
            if agregats:
                instruction = pg_insert(EvaluationReport).values(
                    [
                        {
                            "execution_id": execution_id,
                            "field_spec_id": field_spec_id,
                            "field_key": agregat.field_key,
                            "compared": agregat.compared,
                            "diff_count": agregat.diff_count,
                        }
                        for field_spec_id, agregat in agregats.items()
                    ]
                )
                await db.execute(
                    instruction.on_conflict_do_update(
                        constraint="uq_evaluation_report_execution_field_spec",
                        set_={
                            "compared": instruction.excluded.compared,
                            "diff_count": instruction.excluded.diff_count,
                        },
                    )
                )
            await db.execute(
                update(TestExecution)
                .where(TestExecution.id == execution_id)
                .values(
                    status=statut.value,
                    finished_at=datetime.now(timezone.utc),
                    confidence_histogram=histogramme,
                    error_message=message,
                )
            )
