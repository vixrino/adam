"""Tests unitaires adam_worker/benchmark/depot.py : les lectures du depot.

test_benchmark.py couvre deja les ecritures (enregistrer_document, terminer,
echouer_bloquees). Ici, la reservation d'une execution, les lectures du
perimetre et le controle d'interruption, contre une fausse session qui rend,
appel apres appel, les resultats prepares.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, AsyncIterator, List

import pytest
from sqlalchemy.dialects import postgresql

from adam_core.db.base import Base
from adam_core.enums.status import TestExecutionStatus
from adam_worker.benchmark import depot as depot_module
from adam_worker.benchmark.depot import DepotBenchmark, ExecutionReservee


class _Resultat:
    """Ce que rend session.execute : seules les methodes lues par le depot."""

    def __init__(self, valeur: Any) -> None:
        self.valeur = valeur

    def scalar_one_or_none(self) -> Any:
        return self.valeur

    def one(self) -> Any:
        return self.valeur

    def all(self) -> Any:
        return self.valeur


class _Session:
    def __init__(self, reponses: List[Any]) -> None:
        self.reponses = list(reponses)
        self.instructions: List[Any] = []
        self.flushs = 0

    async def execute(self, instruction: Any) -> _Resultat:
        self.instructions.append(instruction)
        return _Resultat(self.reponses.pop(0) if self.reponses else None)

    async def flush(self) -> None:
        self.flushs += 1


@pytest.fixture(name="brancher")
def _brancher_fixture(monkeypatch: pytest.MonkeyPatch) -> Any:
    def _brancher(*reponses: Any) -> _Session:
        session = _Session(list(reponses))

        @asynccontextmanager
        async def fausse(**_: Any) -> AsyncIterator[_Session]:
            yield session

        monkeypatch.setattr(depot_module, "get_async_session", fausse)
        return session

    return _brancher


def _sql(instruction: Any) -> str:
    """SQL compile sans prefixe de schema, pour valoir dans adam comme dans nota."""
    sql = str(instruction.compile(dialect=postgresql.dialect()))
    schema = Base.metadata.schema
    return sql.replace(f"{schema}.", "") if schema else sql


# -- reserver_execution -----------------------------------------------------------


def test_rien_a_reserver(brancher: Any) -> None:
    session = brancher(None)

    assert asyncio.run(DepotBenchmark().reserver_execution()) is None
    assert session.flushs == 0
    sql = _sql(session.instructions[0])
    # Deux workers ne prennent jamais la meme execution.
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "ORDER BY test_execution.created_at" in sql


def test_reserver_passe_l_execution_en_running(brancher: Any) -> None:
    execution = SimpleNamespace(id=7, recipe_id=3, status="PENDING", started_at=None)
    recette = SimpleNamespace(
        status="LOCKED",
        document_ids=[12, 15],
        config={"score_minimal": 0.85},
        schema_id=2,
        schema_hash="abc",
        verite_empreintes={"12": "h12"},
    )
    session = brancher(execution, recette)

    reservee = asyncio.run(DepotBenchmark().reserver_execution())

    assert reservee == ExecutionReservee(
        id=7,
        recipe_id=3,
        recipe_status="LOCKED",
        document_ids=[12, 15],
        schema_id=2,
        config={"score_minimal": 0.85},
        schema_hash_export="abc",
        verite_export={"12": "h12"},
    )
    assert execution.status == TestExecutionStatus.RUNNING.value
    assert execution.started_at is not None
    assert session.flushs == 1
    # Le schema fige par l'export, sinon celui du dataset (recettes d'avant les exports).
    assert "coalesce(dataset_export.schema_id, dataset.schema_id)" in _sql(session.instructions[1])


def test_reserver_une_recette_sans_documents_ni_config(brancher: Any) -> None:
    execution = SimpleNamespace(id=8, recipe_id=4, status="PENDING", started_at=None)
    recette = SimpleNamespace(
        status="LOCKED",
        document_ids=None,
        config=None,
        schema_id="5",
        schema_hash=None,
        verite_empreintes=None,
    )
    brancher(execution, recette)

    reservee = asyncio.run(DepotBenchmark().reserver_execution())

    assert reservee is not None
    assert reservee.document_ids == [] and reservee.config == {}
    assert reservee.schema_id == 5
    assert reservee.schema_hash_export is None and reservee.verite_export is None


# -- noter_moteur, identifier, schema ---------------------------------------------


def test_noter_moteur(brancher: Any) -> None:
    session = brancher()

    asyncio.run(DepotBenchmark().noter_moteur(7, "mistral", "mistral-ocr-latest"))

    sql = _sql(session.instructions[0])
    assert "UPDATE test_execution SET ocr_provider=" in sql and "ocr_model_id=" in sql


def test_identifier(brancher: Any) -> None:
    session = brancher()

    asyncio.run(DepotBenchmark().identifier(7, "comparateur-v3", "hash"))

    sql = _sql(session.instructions[0])
    assert "comparateur_version=" in sql and "schema_hash=" in sql


def test_schema_delegue_a_schema_en_dict(brancher: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    session = brancher()
    vus: List[Any] = []

    async def faux_schema_en_dict(db: Any, schema_id: int) -> dict[str, Any]:
        vus.append((db, schema_id))
        return {"name": "CERFA", "pages": [], "field_specs": []}

    monkeypatch.setattr(depot_module, "schema_en_dict", faux_schema_en_dict)

    assert asyncio.run(DepotBenchmark().schema(2)) == {
        "name": "CERFA",
        "pages": [],
        "field_specs": [],
    }
    assert vus == [(session, 2)]


# -- documents ---------------------------------------------------------------------


def test_documents_dans_l_ordre_de_la_recette(brancher: Any) -> None:
    # La base rend les lignes dans un ordre quelconque, et le document 99 a disparu.
    brancher([(15, 150), (12, 120)])

    assert asyncio.run(DepotBenchmark().documents([12, 99, 15])) == [(12, 120), (15, 150)]


# -- verite -------------------------------------------------------------------------


def test_verite_dans_l_ordre_du_schema(brancher: Any) -> None:
    df = SimpleNamespace(id=1, group_id="pret_2", resolved_value="1200")
    fs = SimpleNamespace(
        id=10,
        section_id="credits",
        field_key="credits.montant",
        value_type="NUMBER",
        sensitive=None,
        page=10,
    )
    session = brancher([(df, fs, True)])

    (champ,) = asyncio.run(DepotBenchmark().verite(42))

    assert champ.document_field_id == 1 and champ.field_spec_id == 10
    assert champ.group_id == "pret_2" and champ.attendu == "1200"
    assert champ.verifie is True and champ.sensitive is False and champ.page == 10
    sql = _sql(session.instructions[0])
    assert "ORDER BY field_spec.page, field_spec.display_order, field_spec.id" in sql
    # Un champ est verifie s'il porte au moins une proposition humaine.
    assert "EXISTS" in sql and "field_proposal" in sql


# -- interrompue --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("statut", "interrompue"),
    [
        (TestExecutionStatus.RUNNING.value, False),
        (TestExecutionStatus.CANCELLED.value, True),
        (TestExecutionStatus.FAILED.value, True),
        (None, True),  # execution supprimee
    ],
)
def test_interrompue(brancher: Any, statut: Any, interrompue: bool) -> None:
    brancher(statut)

    assert asyncio.run(DepotBenchmark().interrompue(7)) is interrompue
