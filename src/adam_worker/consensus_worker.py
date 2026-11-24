"""
Consensus Worker retry des documents en attente de résolution.

Tourne périodiquement et relance try_resolve sur les documents
qui ont atteint required_operators jobs submitted mais ne sont
pas encore VALIDATED (echec background task ou conflit non resolu).

Sprint 2 : logique de polling implementee, a refiner dans la Sprint 3
"""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select

from adam_api.services.consensus import try_resolve
from adam_core.db.session import get_async_session
from adam_core.enums.status import DocumentStatus
from adam_core.models import Document
from adam_core.utils.logging import get_logger
from adam_worker.base_worker import BaseWorker

logger = get_logger(__name__)


async def run_pending_consensus() -> None:
    """
    Cherche tous les documents PENDING_CONSENSUS et tente de resoudre
    leur consensus.

    Idempotent : try_resolve gere les gardes internes (count, already validated).
    """
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

        resultats: Counter[str] = Counter()
        for doc_id, dataset_id in pending:
            try:
                outcome = await try_resolve(doc_id, dataset_id)
                resultats[str(outcome.get("status") or "error")] += 1
            except Exception:
                logger.exception("consensus_worker: echec [document_id=%s]", doc_id)
                resultats["error"] += 1
        logger.info(
            "consensus_worker: cycle termine [documents=%s resultats=%s]",
            len(pending),
            dict(resultats),
        )


# TODO Sprint 3 : brancher dans le scheduler (à definir)
class ConsensusWorker(BaseWorker):

    async def poll(self) -> None:
        await run_pending_consensus()
