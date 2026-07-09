"""Consensus Worker : retry des documents en attente de resolution.

Relance try_resolve sur les documents qui ont atteint required_operators
jobs submitted mais ne sont pas encore VALIDATED (echec de la background
task declenchee depuis submit_job, ou conflit non resolu). Idempotent :
try_resolve gere ses propres gardes internes (compte de jobs soumis,
document deja VALIDATED), donc relancer un document deja resolu est sans
effet.
"""

from __future__ import annotations

from sqlalchemy import select

from adam_api.services.consensus import try_resolve
from adam_core.db.session import get_async_session
from adam_core.enums.status import DocumentStatus
from adam_core.models import Document
from adam_worker.base_worker import BaseWorker


class ConsensusWorker(BaseWorker):
    """Cherche les documents PENDING_CONSENSUS et tente de resoudre leur consensus."""

    async def poll(self) -> None:
        async with get_async_session() as db:
            pending = (
                await db.execute(
                    select(Document.id, Document.dataset_id).where(
                        Document.status == DocumentStatus.PENDING_CONSENSUS.value
                    )
                )
            ).all()
        if not pending:
            self.logger.debug("aucun document en attente")
            return
        self.logger.info("%s document(s) a traiter", len(pending))
        for doc_id, dataset_id in pending:
            try:
                await try_resolve(doc_id, dataset_id)
            except Exception:
                self.logger.exception("echec [document_id=%s]", doc_id)
