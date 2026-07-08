"""Consensus Worker : retry le calcul de consensus des documents en attente."""

from __future__ import annotations

from sqlalchemy import select

from adam_api.services.consensus import try_resolve
from adam_core.db.session import get_async_session
from adam_core.enums.status import DocumentStatus
from adam_core.models import Document
from adam_worker.base_worker import BaseWorker


class ConsensusWorker(BaseWorker):
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
