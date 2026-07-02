"""Service de consensus majoritaire sur les champs document."""

from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from adam_core.db.session import get_async_session
from adam_core.enums.status import DocumentFieldStatus, DocumentStatus, JobState
from adam_core.models import Dataset, Document, DocumentField, FieldProposal, Job
from adam_core.utils.logging import get_logger

logger = get_logger(__name__)


async def try_resolve(document_id: int, dataset_id: int) -> dict[str, Any]:
    """
    Tente de resoudre le consensus pour un document.
    Declenchement : background task depuis submit_job.
    """
    try:
        async with get_async_session() as db:
            return await _resolve(document_id, dataset_id, db)
    except Exception:
        logger.exception("try_resolve echoue [document_id=%s dataset_id=%s]", document_id, dataset_id)
        return {"error": "try_resolve echoue", "document_id": document_id}


def _apply_vote(df: DocumentField, field_proposals: list[FieldProposal]) -> bool:
    if not field_proposals:
        df.consensus_reached = True
        df.resolved_value = df.ocr_value
        df.status = DocumentFieldStatus.VALIDATED.value
        return True
    values = [p.value for p in field_proposals]
    top_value, top_count = Counter(values).most_common(1)[0]
    if top_count > len(values) / 2:
        df.consensus_reached = True
        df.resolved_value = top_value
        df.status = DocumentFieldStatus.VALIDATED.value
        return True
    df.consensus_reached = False
    df.status = DocumentFieldStatus.DISPUTED.value
    return False


async def _resolve(document_id: int, dataset_id: int, db: AsyncSession) -> dict[str, Any]:
    dataset = await db.get(Dataset, dataset_id)
    if not dataset:
        return {"document_id": document_id, "status": "error", "reason": "dataset introuvable"}
    document = await db.get(Document, document_id)
    if not document:
        return {"document_id": document_id, "status": "error", "reason": "document introuvable"}
    if document.status == DocumentStatus.VALIDATED.value:
        return {"document_id": document_id, "status": "already_validated"}
    submitted_count: int = (
        await db.execute(
            select(count(Job.id))
            .where(Job.document_id == document_id)
            .where(Job.state == JobState.SUBMITTED.value)
        )
    ).scalar_one()
    if submitted_count < dataset.required_operators:
        return {
            "document_id": document_id,
            "status": "waiting",
            "submitted_jobs": submitted_count,
            "required_operators": dataset.required_operators,
        }
    fields = (
        (await db.execute(select(DocumentField).where(DocumentField.document_id == document_id)))
        .scalars()
        .all()
    )
    proposals = (
        (
            await db.execute(
                select(FieldProposal)
                .join(Job, FieldProposal.job_id == Job.id)
                .where(Job.document_id == document_id)
                .where(Job.state == JobState.SUBMITTED.value)
            )
        )
        .scalars()
        .all()
    )
    by_field: dict[int, list[FieldProposal]] = {}
    for p in proposals:
        by_field.setdefault(p.document_field_id, []).append(p)
    all_resolved = all(_apply_vote(df, by_field.get(df.id, [])) for df in fields)
    disputed_count = sum(1 for df in fields if df.status == DocumentFieldStatus.DISPUTED.value)
    if all_resolved:
        document.status = DocumentStatus.VALIDATED.value
        logger.info("document valide [document_id=%s]", document_id)
    else:
        logger.info(
            "consensus partiel [document_id=%s disputed=%s/%s]",
            document_id,
            disputed_count,
            len(fields),
        )
    return {
        "document_id": document_id,
        "document_status": document.status,
        "fields_total": len(fields),
        "fields_resolved": len(fields) - disputed_count,
        "fields_disputed": disputed_count,
        "submitted_jobs": submitted_count,
    }
