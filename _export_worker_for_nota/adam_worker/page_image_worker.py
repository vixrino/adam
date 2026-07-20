"""Mini worker de generation des images de page (Sprint 3, ticket 8).

Polling sur DOCUMENT.status == RECEIVED : convertit chaque page du PDF
source (lu depuis le PVC via FILE) en PNG ecrit dans file_id/pages/,
renseigne FILE.page_count, puis passe le Document a IN_PROGRESS.

Chaque Document est traite dans sa propre transaction, verrouillee avec
`FOR UPDATE SKIP LOCKED` : si plusieurs instances du worker tournent en
parallele (ou si deux cycles de polling se chevauchent), un seul worker
obtient la ligne et les autres l'ignorent silencieusement (CA-6). Un echec
de rendu (PDF corrompu, page illisible) est logue avec le document_id et
laisse le Document en RECEIVED pour un prochain essai (CA-5).
"""

from __future__ import anadamtions

from pathlib import Path
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adam_api.core.config import settings
from adam_core.db.session import get_async_session
from adam_core.enums.status import DocumentStatus
from adam_core.models import Document, File
from adam_core.utils.pdf_render import PdfRenderError, pages_relative_dir, render_pages_to_png
from adam_worker.base_worker import BaseWorker

_BATCH_SIZE = 20


class PageImageWorker(BaseWorker):
    """Genere les images PNG de page pour les Document en statut RECEIVED."""

    def __init__(self, pvc_root: Optional[Path] = None) -> None:
        super().__init__()
        self.pvc_root = pvc_root or Path(settings.pvc_mount_path)

    async def poll(self) -> None:
        candidate_ids = await self._fetch_candidate_ids()
        if not candidate_ids:
            self.logger.debug("aucun document RECEIVED")
            return
        self.logger.info("%s document(s) RECEIVED a traiter", len(candidate_ids))
        for document_id in candidate_ids:
            try:
                await self._process_one(document_id)
            except Exception:
                self.logger.exception(
                    "echec inattendu generation images [document_id=%s]", document_id
                )

    async def _fetch_candidate_ids(self) -> List[int]:
        async with get_async_session() as db:
            rows = (
                (
                    await db.execute(
                        select(Document.id)
                        .where(Document.status == DocumentStatus.RECEIVED.value)
                        .limit(_BATCH_SIZE)
                    )
                )
                .scalars()
                .all()
            )
            return list(rows)

    async def _process_one(self, document_id: int) -> None:
        async with get_async_session() as db:
            document = await self._lock_document(db, document_id)
            if document is None:
                return  # deja traite ou verrouille par un autre worker (CA-6)

            file_row = await db.get(File, document.file_id)
            if file_row is None:
                self.logger.error(
                    "FILE introuvable [document_id=%s file_id=%s]", document_id, document.file_id
                )
                return

            pdf_path = self.pvc_root / file_row.file_path
            output_dir = self.pvc_root / pages_relative_dir(file_row.id)
            try:
                written = render_pages_to_png(pdf_path, output_dir)
            except PdfRenderError as exc:
                self.logger.warning(
                    "PDF illisible, document laisse en RECEIVED [document_id=%s file_id=%s]: %s",
                    document_id,
                    file_row.id,
                    exc,
                )
                return

            file_row.page_count = len(written)
            document.status = DocumentStatus.IN_PROGRESS.value
            self.logger.info(
                "Images generees [document_id=%s file_id=%s pages=%s]",
                document_id,
                file_row.id,
                len(written),
            )

    async def _lock_document(self, db: AsyncSession, document_id: int) -> Optional[Document]:
        document = (
            await db.execute(
                select(Document).where(Document.id == document_id).with_for_update(skip_locked=True)
            )
        ).scalar_one_or_none()
        if document is None or document.status != DocumentStatus.RECEIVED.value:
            return None
        return document
