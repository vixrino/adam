"""L'unicite d'un job vivant par (document, agent) est portee par le modele."""

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from adam_core.models import Job


def _index():
    (index,) = [i for i in Job.__table__.indexes if i.name == "uq_job_agent_document_active"]
    return index


def test_one_live_job_per_document_and_agent() -> None:
    index = _index()
    assert index.unique is True
    assert [c.name for c in index.columns] == ["document_id", "agent_id"]


def test_cancelled_jobs_are_outside_the_constraint() -> None:
    """Partiel : sans cela un operateur dont le job a ete annule n'en recevrait jamais un autre."""
    ddl = str(CreateIndex(_index()).compile(dialect=postgresql.dialect()))
    assert "CREATE UNIQUE INDEX uq_job_agent_document_active" in ddl
    assert "WHERE state <> 'CANCELLED'" in ddl
