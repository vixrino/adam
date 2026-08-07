"""Worker de pre-alimentation OCR : polling des documents INGESTED.

Un document ingere porte ses images mais aucun champ. Ce worker les lui donne :
il soumet les images a l'OCR, recupere le schema attendu via le dataset, fusionne
les deux, cree les DOCUMENT_FIELD par l'API, et fait passer le document en
IN_PROGRESS.

Ce qui passe par la base et ce qui passe par HTTP
-------------------------------------------------
Le polling et la transition de statut se font en base directe, comme les autres
workers. La lecture du schema et la creation des champs passent par l'API : la
validation de coherence field_spec/schema et la contrainte d'unicite y vivent
deja, les dupliquer ici serait le debut d'une divergence.

Isolation des erreurs
---------------------
Un document a la fois, chacun dans son propre try. Une erreur le fait passer en
ERROR — et non rester en INGESTED, ou il serait repolle indefiniment et
bloquerait le lot — puis la boucle continue avec le suivant.

Un OCR indisponible n'est pas une erreur : le document est pre-alimente avec des
champs vides et passe quand meme en IN_PROGRESS, l'operateur saisira tout. Seul
un echec technique du connecteur ou de l'API met le document en ERROR.

Confidentialite des logs
------------------------
Aucune valeur de champ n'est loguee, jamais. Les documents traites contiennent
des IBAN et des NIR ; les logs de ce worker ne portent que des identifiants et
des comptages, dont le nombre de champs detectes, qui suffit au diagnostic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select, update

from adam_api.core.config import API_PREFIX, settings
from adam_core.db.session import get_async_session
from adam_core.enums.status import DocumentStatus
from adam_core.models import Document
from adam_core.schemas.interface_contract import SmartdocDocument
from adam_worker.base_worker import BaseWorker
from adam_worker.connectors.base import BaseOcrConnector, OcrConnectorError
from adam_worker.connectors.mock import MockOcrConnector
from adam_worker.prepopulation.api_client import ApiClient, ApiClientError
from adam_worker.prepopulation.merger import count_detected, merge

_BATCH_SIZE = 20
_DEFAULT_POLL_INTERVAL = 30.0


def default_pages_dir(file_id: int) -> Path:
    """Repertoire des images de page, relatif a la racine du PVC.

    La convention est celle du pipeline d'ingestion : file_id/pages/. Elle est
    redefinie ici plutot qu'importee de utils.pdf_render, ou elle vit aussi :
    ce module la importe PyMuPDF, et faire dependre la pre-alimentation d'un
    moteur de rendu PDF pour une concatenation de chemin serait une dette
    gratuite — le worker ne rend aucune image, il les lit.

    Le resolveur est injectable via `pages_dir` : si la convention change, ou
    differe entre deux deploiements, elle se surcharge sans toucher au worker.
    """
    return Path(str(file_id)) / "pages"


class PrepopulationError(Exception):
    """Echec bloquant sur un document : il passera en ERROR."""


class PrepopulationWorker(BaseWorker):
    """Pre-alimente les champs des documents en statut INGESTED."""

    poll_interval_seconds = _DEFAULT_POLL_INTERVAL

    def __init__(
        self,
        connector: Optional[BaseOcrConnector] = None,
        api_client: Optional[ApiClient] = None,
        *,
        batch_size: int = _BATCH_SIZE,
        pvc_root: Optional[Path] = None,
        poll_interval_seconds: Optional[float] = None,
        pages_dir: Callable[[int], Path] = default_pages_dir,
    ) -> None:
        super().__init__()
        self.connector = connector or MockOcrConnector()
        self.api_client = api_client or ApiClient(
            # API_PREFIX est celui que main.py monte : sans lui, chaque appel
            # part en 404, que le worker traduirait en documents ERROR sans
            # que la vraie cause apparaisse nulle part.
            base_url=f"http://{settings.api_host}:{settings.api_port}{API_PREFIX}",
            timeout_seconds=float(settings.ocr_timeout_seconds),
        )
        self.batch_size = batch_size
        self.pvc_root = pvc_root or Path(settings.pvc_mount_path)
        self.pages_dir = pages_dir
        if poll_interval_seconds is not None:
            self.poll_interval_seconds = poll_interval_seconds

    # -- Boucle -------------------------------------------------------------

    async def poll(self) -> None:
        candidates = await self._fetch_candidates()
        if not candidates:
            self.logger.debug("aucun document INGESTED")
            return

        self.logger.info("%s document(s) INGESTED a pre-alimenter", len(candidates))
        for document_id in candidates:
            try:
                await self._process_one(document_id)
            except PrepopulationError as exc:
                # Echec attendu et deja diagnostique : on sort le document de la
                # file plutot que de le laisser repoller sans fin.
                self.logger.error(
                    "pre-alimentation impossible, document en ERROR [document_id=%s] : %s",
                    document_id,
                    exc,
                )
                await self._set_status(document_id, DocumentStatus.ERROR)
            except Exception:  # pylint: disable=broad-exception-caught
                # Filet : un imprevu ne doit pas interrompre le lot.
                self.logger.exception("echec inattendu [document_id=%s]", document_id)
                await self._set_status(document_id, DocumentStatus.ERROR)

    async def _fetch_candidates(self) -> List[int]:
        """Documents prets, les plus anciens d'abord."""
        async with get_async_session() as db:
            rows = (
                (
                    await db.execute(
                        select(Document.id)
                        .where(Document.status == DocumentStatus.INGESTED.value)
                        .order_by(Document.created_at)
                        .limit(self.batch_size)
                    )
                )
                .scalars()
                .all()
            )
            return list(rows)

    # -- Traitement d'un document -------------------------------------------

    async def _process_one(self, document_id: int) -> None:
        dataset_id, file_id = await self._load_context(document_id)
        images = self._page_images(file_id)

        ocr = await self._run_ocr(images, document_id)
        field_specs = await self._load_field_specs(dataset_id, document_id)

        payloads = merge(field_specs, ocr)
        if not payloads:
            raise PrepopulationError(f"schema du dataset {dataset_id} sans field_spec")

        try:
            result = await self.api_client.create_fields_bulk(document_id, payloads)
        except ApiClientError as exc:
            raise PrepopulationError(f"creation des champs refusee : {exc}") from exc

        await self._set_status(document_id, DocumentStatus.IN_PROGRESS)
        self.logger.info(
            "document pre-alimente [document_id=%s dataset_id=%s champs=%s "
            "detectes=%s crees=%s ignores=%s ocr=%s]",
            document_id,
            dataset_id,
            len(payloads),
            count_detected(payloads),
            len(result.get("created", [])),
            len(result.get("skipped", [])),
            "oui" if ocr is not None else "non",
        )

    async def _load_context(self, document_id: int) -> Tuple[int, int]:
        async with get_async_session() as db:
            row = (
                await db.execute(
                    select(Document.dataset_id, Document.file_id).where(
                        Document.id == document_id
                    )
                )
            ).one_or_none()
        if row is None:
            raise PrepopulationError("document introuvable")
        return int(row.dataset_id), int(row.file_id)

    def _page_images(self, file_id: int) -> List[Path]:
        """Images de page ecrites par le pipeline d'ingestion.

        Leur absence n'est pas bloquante : le connecteur recevra une liste vide
        et ne detectera rien, ce qui produit un document a champs vides. C'est
        preferable a un ERROR, l'operateur pouvant tout saisir a la main.
        """
        directory = self.pvc_root / self.pages_dir(file_id)
        if not directory.is_dir():
            return []
        return sorted(directory.glob("*.png"))

    async def _run_ocr(
        self, images: Sequence[Path], document_id: int
    ) -> Optional[SmartdocDocument]:
        try:
            ocr = await self.connector.extract(images)
        except OcrConnectorError as exc:
            raise PrepopulationError(f"connecteur OCR en echec : {exc}") from exc
        if ocr is None:
            # Cas nominal : on pre-alimente des champs vides.
            self.logger.warning(
                "OCR sans resultat, champs vides [document_id=%s connecteur=%s]",
                document_id,
                self.connector.name,
            )
        return ocr

    async def _load_field_specs(
        self, dataset_id: int, document_id: int
    ) -> List[Dict[str, Any]]:
        try:
            return await self.api_client.get_field_specs(dataset_id)
        except ApiClientError as exc:
            raise PrepopulationError(
                f"schema injoignable pour le document {document_id} : {exc}"
            ) from exc

    async def _set_status(self, document_id: int, status: DocumentStatus) -> None:
        async with get_async_session() as db:
            await db.execute(
                update(Document).where(Document.id == document_id).values(status=status.value)
            )


__all__ = ["PrepopulationWorker", "PrepopulationError"]
