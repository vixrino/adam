"""
Consensus Worker retry des documents en attente de resolution.
"""

from __future__ import annotations

from sqlalchemy import select

from adam_api.services.consensus import try_resolve
from adam_core.db.session import get_async_session
from adam_core.enums.status import DocumentStatus
from adam_core.models import Document
from adam_core.utils.logging import get_logger

logger = get_logger(__name__)


async def run_pending_consensus() -> None:
    async with get_async_session() as db:
        pending = (
            await db.execute(
                select(Document.id, Document.dataset_id).where(
                    Document.status == DocumentStatus.PENDING_CONSENSUS.value
                )
            )
        ).all()
        if not pending:
            logger.debug("consensus_worker: aucun document en attente")
            return
        logger.info("consensus_worker: %s document(s) a traiter", len(pending))
        for doc_id, dataset_id in pending:
            try:
                await try_resolve(doc_id, dataset_id)
            except Exception:
                logger.exception("consensus_worker: echec [document_id=%s]", doc_id)
