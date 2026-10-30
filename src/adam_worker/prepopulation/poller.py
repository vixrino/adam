"""Worker de pre-alimentation OCR : polling des documents INGESTED.

Un document ingere porte ses images mais aucun champ. Ce worker les lui donne :
il soumet les images a l'OCR, lit le schema attendu via le dataset, fusionne
les deux, cree les DOCUMENT_FIELD, et fait passer le document en IN_PROGRESS.

Tout passe par la base
----------------------
Le worker n'appelle pas l'API : le middleware exa-pie exige un JWT sur chaque
route, que le X-Internal-Token d'un service ne fournit pas (400 "token not
found"). La creation des champs reutilise adam_api.services.document_fields, ou
vivent la validation de coherence field_spec/schema et la contrainte d'unicite :
une seule implementation, appelee par la route comme par le worker.

Isolation des erreurs
---------------------
Un document a la fois, chacun dans son propre try. Une erreur le fait passer en
ERROR — et non rester en INGESTED, ou il serait repolle indefiniment et
bloquerait le lot — puis la boucle continue avec le suivant.

Un OCR indisponible n'est pas une erreur : le document est pre-alimente avec des
champs vides et passe quand meme en IN_PROGRESS, l'operateur saisira tout. Un
echec technique du connecteur ou de l'API met le document en ERROR, de meme
qu'un document que l'OCR juge non conforme : aucune page du formulaire
reconnue, ou des pages a champs introuvables. Le motif de l'ERROR est ecrit
dans metadata["erreur"] du document, que l'API expose.

Remise en ordre des images
--------------------------
Quand l'OCR a reconnu des pages hors de leur rang — un CERFA scanne pages 9
et 10 inversees — le worker renomme les images de page pour que l'image N
porte la page N du formulaire. Sans cela, l'operateur verrait les champs de
la page 9 poses sur l'image de la page 10. Les images appartiennent au FILE,
partage entre documents de meme contenu : ce contenu-la est dans le meme
desordre, la remise en ordre vaut pour tous.

Le PDF suit : une copie aux pages remises en ordre est ecrite a cote de
l'original, sous <nom>_ordonne.pdf, et FILE.file_path pointe desormais vers
elle — c'est elle que sert /files/{id}/content. L'original reste sur le PVC,
trace du scan tel que recu. sha256_checksum reste celui de l'upload : c'est
la cle de deduplication, et le meme PDF redepose retrouve un FILE deja en
ordre.

Confidentialite des logs
------------------------
Aucune valeur de champ n'est loguee, jamais. Les documents traites contiennent
des IBAN et des NIR ; les logs de ce worker ne portent que des identifiants et
des comptages, dont le nombre de champs detectes, qui suffit au diagnostic.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import case, func, literal, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import selectinload

from adam_api.core.config import settings
from adam_api.exceptions.document_fields import FieldSpecMismatch
from adam_api.services import document_fields
from adam_core.db.session import get_async_session
from adam_core.enums.status import DocumentStatus
from adam_core.models import DocSchema, Dataset, Document, File
from adam_core.schemas.interface_contract import SmartdocDocument
from adam_core.utils.pdf_render import PdfRenderError, reorder_pdf
from adam_worker.base_worker import BaseWorker
from adam_worker.connectors import connector_from_settings
from adam_worker.connectors.base import (
    BaseOcrConnector,
    DocumentNonConforme,
    OcrConnectorError,
)
from adam_worker.connectors.modele import ModeleDocument
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
    """Echec bloquant sur un document : il passera en ERROR.

    `details` complete le motif ecrit dans metadata["erreur"].
    """

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.details = details or {}


class PrepopulationWorker(BaseWorker):
    """Pre-alimente les champs des documents en statut INGESTED."""

    poll_interval_seconds = _DEFAULT_POLL_INTERVAL

    def __init__(
        self,
        connector: Optional[BaseOcrConnector] = None,
        *,
        batch_size: int = _BATCH_SIZE,
        pvc_root: Optional[Path] = None,
        poll_interval_seconds: Optional[float] = None,
        pages_dir: Callable[[int], Path] = default_pages_dir,
    ) -> None:
        super().__init__()
        self.connector = connector or connector_from_settings(settings)
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

        # En DEBUG : chaque document du lot emet ensuite sa propre ligne, avec le
        # detail qui compte. Annoncer le decompte n'ajoutait rien devant N lignes
        # qui le disent.
        self.logger.debug("%s document(s) INGESTED a pre-alimenter", len(candidates))
        cycle_started = perf_counter()
        pre_alimentes = 0
        en_erreur = 0
        champs_crees = 0
        for document_id in candidates:
            try:
                champs_crees += await self._process_one(document_id)
                pre_alimentes += 1
            except PrepopulationError as exc:
                en_erreur += 1
                # Echec attendu et deja diagnostique : on sort le document de la
                # file plutot que de le laisser repoller sans fin.
                self.logger.error(
                    "pre-alimentation impossible, document en ERROR [document_id=%s] : %s",
                    document_id,
                    exc,
                )
                await self._set_error(document_id, {"message": str(exc), **exc.details})
            except Exception:  # pylint: disable=broad-exception-caught
                # Filet : un imprevu ne doit pas interrompre le lot.
                en_erreur += 1
                self.logger.exception("echec inattendu [document_id=%s]", document_id)
                await self._set_error(
                    document_id, {"message": "echec inattendu, voir les logs du worker"}
                )
        # Bilan du cycle : INGESTED -> IN_PROGRESS (champs crees) ou ERROR (motif en metadata).
        self.logger.info(
            "cycle termine [documents=%s pre_alimentes=%s error=%s champs_crees=%s duree=%.2fs]",
            len(candidates),
            pre_alimentes,
            en_erreur,
            champs_crees,
            perf_counter() - cycle_started,
        )

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

    async def _process_one(self, document_id: int) -> int:
        """Pre-alimente un document ; retourne le nombre de champs crees."""
        dataset_id, file_id, file_path = await self._load_context(document_id)
        images = self._page_images(file_id)

        # Le schema passe avant l'OCR : c'est lui qui dit au connecteur quels
        # champs extraire et a quoi ressemble chaque page.
        schema = await self._load_schema(dataset_id, document_id)
        field_specs: List[Dict[str, Any]] = schema.get("field_specs") or []
        modele = ModeleDocument.depuis_schema(schema)

        ocr = await self._run_ocr(images, document_id, modele)
        _controle_pages(ocr)
        await self._remettre_en_ordre(document_id, file_id, file_path, images, ocr)

        payloads = merge(field_specs, ocr)
        if not payloads:
            raise PrepopulationError(f"schema du dataset {dataset_id} sans field_spec")

        result = await self._create_fields(document_id, payloads)

        await self._set_status(document_id, DocumentStatus.IN_PROGRESS)
        self.logger.info(
            "document pre-alimente [document_id=%s dataset_id=%s champs=%s "
            "detectes=%s crees=%s ignores=%s ocr=%s]",
            document_id,
            dataset_id,
            len(payloads),
            count_detected(payloads),
            len(result.created),
            len(result.skipped),
            "oui" if ocr is not None else "non",
        )
        return len(result.created)

    async def _load_context(self, document_id: int) -> Tuple[int, int, str]:
        async with get_async_session() as db:
            row = (
                await db.execute(
                    select(Document.dataset_id, Document.file_id, File.file_path)
                    .join(File, Document.file_id == File.id)
                    .where(Document.id == document_id)
                )
            ).one_or_none()
        if row is None:
            raise PrepopulationError("document introuvable")
        return int(row.dataset_id), int(row.file_id), str(row.file_path)

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
        self, images: Sequence[Path], document_id: int, modele: ModeleDocument
    ) -> Optional[SmartdocDocument]:
        try:
            ocr = await self.connector.extract(images, modele)
        except DocumentNonConforme as exc:
            raise PrepopulationError(
                f"document non conforme : {exc}",
                {"motif": "document_non_conforme", "anomalies_pages": exc.anomalies},
            ) from exc
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

    async def _load_schema(self, dataset_id: int, document_id: int) -> Dict[str, Any]:
        """Schema du dataset sous la forme que lisent le modele OCR et le merger."""
        async with get_async_session() as db:
            schema = (
                await db.execute(
                    select(DocSchema)
                    .join(Dataset, Dataset.schema_id == DocSchema.id)
                    .where(Dataset.id == dataset_id)
                    .options(selectinload(DocSchema.field_specs), selectinload(DocSchema.pages))
                )
            ).scalar_one_or_none()
            if schema is None:
                raise PrepopulationError(
                    f"schema introuvable pour le document {document_id} (dataset {dataset_id})"
                )
            return {
                "name": schema.name,
                "pages": [
                    {"page_number": p.page_number, "description": p.description}
                    for p in schema.pages
                ],
                "field_specs": [
                    {c.name: getattr(fs, c.name) for c in fs.__table__.columns}
                    for fs in sorted(schema.field_specs, key=lambda x: (x.page, x.display_order))
                ],
            }

    async def _create_fields(
        self, document_id: int, payloads: List[Dict[str, Any]]
    ) -> document_fields.BulkOutcome:
        """Cree les champs avec le service de l'API, dans la transaction du worker."""
        async with get_async_session() as db:
            document = await document_fields.get_document_or_none(db, document_id)
            if document is None:
                raise PrepopulationError("document introuvable")
            try:
                return await document_fields.create_bulk(db, document, payloads)
            except FieldSpecMismatch as exc:
                raise PrepopulationError(f"creation des champs refusee : {exc}") from exc

    async def _set_status(self, document_id: int, status: DocumentStatus) -> None:
        async with get_async_session() as db:
            await db.execute(
                update(Document).where(Document.id == document_id).values(status=status.value)
            )

    async def _set_error(self, document_id: int, erreur: Dict[str, Any]) -> None:
        """Passe le document en ERROR et ecrit le motif dans metadata["erreur"]."""
        await self._update_metadata(
            document_id,
            {"erreur": {"etape": "pre_alimentation", **erreur}},
            status=DocumentStatus.ERROR,
        )

    async def _update_metadata(
        self,
        document_id: int,
        cles: Dict[str, Any],
        *,
        status: Optional[DocumentStatus] = None,
    ) -> None:
        """Ajoute des cles a metadata sans ecraser les autres (concatenation JSONB).

        Seul un objet est conserve comme base. NULL SQL, mais aussi un JSON null
        ecrit avant que la colonne ne l'interdise, repartent d'un objet vide : en
        JSONB, null || {...} ne fusionne pas, il rend le tableau [null, {...}],
        et la reponse de l'API, qui attend un objet, echoue alors en 500.
        """
        base = case(
            (func.jsonb_typeof(Document.metadata_) == "object", Document.metadata_),
            else_=literal({}, JSONB),
        )
        values: Dict[str, Any] = {"metadata_": base.op("||")(literal(cles, JSONB))}
        if status is not None:
            values["status"] = status.value
        async with get_async_session() as db:
            await db.execute(update(Document).where(Document.id == document_id).values(**values))

    async def _remettre_en_ordre(
        self,
        document_id: int,
        file_id: int,
        file_path: str,
        images: Sequence[Path],
        ocr: Optional[SmartdocDocument],
    ) -> None:
        """Remet PDF et images dans l'ordre du formulaire, si l'OCR l'a trouve
        different de l'ordre du scan.

        Le PDF passe en premier : s'il echoue, le document part en ERROR avec
        des images encore intactes, plutot qu'avec des images deplacees et un
        PDF qui ne l'est pas.
        """
        if ocr is None:
            return
        permutation = _permutation(ocr.metadata.get("ordre_pages"), len(images))
        if not permutation:
            return
        pdf_ordonne = await self._reordonner_pdf(file_id, file_path, permutation, len(images))
        self._reordonner_images(images, permutation)

        deplacees = [{"page": page, "rang_origine": rang} for rang, page in permutation.items()]
        self.logger.warning(
            "pages remises dans l'ordre du formulaire [document_id=%s pdf=%s] : %s",
            document_id,
            pdf_ordonne or "non regenere",
            deplacees,
        )
        trace: Dict[str, Any] = {"pages_reordonnees": deplacees}
        if pdf_ordonne:
            trace["pdf_origine"] = file_path
        await self._update_metadata(document_id, trace)

    async def _reordonner_pdf(
        self, file_id: int, file_path: str, permutation: Mapping[int, int], nombre: int
    ) -> Optional[str]:
        """Ecrit <nom>_ordonne.pdf et y fait pointer le FILE ; rend son chemin.

        Un PDF absent du PVC n'empeche pas la remise en ordre des images : il
        est signale et ignore. Rend None dans ce cas.
        """
        source = self.pvc_root / file_path
        if not source.is_file():
            self.logger.warning("PDF absent du PVC, non remis en ordre [file_id=%s]", file_id)
            return None
        # ordre[page - 1] = rang de l'image qui porte cette page.
        ordre = list(range(1, nombre + 1))
        for rang, page in permutation.items():
            ordre[page - 1] = rang
        stem = source.stem.removesuffix("_ordonne")
        destination = source.with_name(f"{stem}_ordonne.pdf")
        try:
            await asyncio.to_thread(reorder_pdf, source, destination, ordre)
        except PdfRenderError as exc:
            raise PrepopulationError(f"PDF non remis en ordre : {exc}") from exc

        nouveau = str(Path(file_path).with_name(destination.name).as_posix())
        async with get_async_session() as db:
            await db.execute(
                update(File)
                .where(File.id == file_id)
                .values(file_path=nouveau, file_size_bytes=destination.stat().st_size)
            )
        return nouveau

    @staticmethod
    def _reordonner_images(images: Sequence[Path], permutation: Mapping[int, int]) -> None:
        """Renomme les images pour que l'image N porte la page N du formulaire.

        Les noms cibles sont ceux des images existantes : l'image de rang r
        prend le nom de l'image de rang p, ou p est la page qu'elle porte. Le
        worker n'a ainsi pas a connaitre la convention de nommage du rendu.
        """
        # Deux passes, pour qu'aucun renommage n'ecrase une image pas encore
        # deplacee : d'abord vers un nom temporaire, puis vers le nom cible.
        temporaires = {}
        for rang in permutation:
            source = images[rang - 1]
            temporaire = source.with_name(source.name + ".reordre")
            source.rename(temporaire)
            temporaires[rang] = temporaire
        for rang, page in permutation.items():
            temporaires[rang].rename(images[page - 1])


def _permutation(ordre_pages: Any, nombre_images: int) -> Dict[int, int]:
    """Rang d'image -> page du formulaire, pour les seules images a deplacer.

    `ordre_pages` (page -> rang) ne couvre que les pages reconnues. Les rangs
    et pages restants — une page blanche que l'OCR n'a pas lue — sont apparies
    dans l'ordre, ce qui laisse en place une page non reconnue quand tout le
    reste l'est. Rend {} quand il n'y a rien a deplacer, ou quand l'ordre ne
    forme pas une permutation des rangs (page hors bornes, rang en double) :
    mieux vaut des images dans l'ordre du scan que dans un ordre invente.
    """
    if not isinstance(ordre_pages, Mapping) or not ordre_pages:
        return {}
    try:
        page_vers_rang = {int(page): int(rang) for page, rang in ordre_pages.items()}
    except (TypeError, ValueError):
        return {}
    bornes = set(range(1, nombre_images + 1))
    pages, rangs = set(page_vers_rang), set(page_vers_rang.values())
    if not pages <= bornes or not rangs <= bornes or len(rangs) != len(pages):
        return {}
    for page, rang in zip(sorted(bornes - pages), sorted(bornes - rangs)):
        page_vers_rang[page] = rang
    return {rang: page for page, rang in page_vers_rang.items() if rang != page}


def _controle_pages(ocr: Optional[SmartdocDocument]) -> None:
    """Bloque un document dont des pages a champs sont introuvables.

    Le connecteur le signale sans lever : une page manquante n'empeche pas
    d'annoter les autres. Mais un formulaire incomplet ne peut pas etre traite,
    et le pre-alimenter laisserait croire le contraire a l'operateur.
    """
    if ocr is None:
        return
    anomalies = ocr.metadata.get("anomalies_pages") or []
    manquantes = [a for a in anomalies if a.get("type") == "pages_manquantes"]
    if manquantes:
        pages = manquantes[0].get("pages")
        raise PrepopulationError(
            f"pages du formulaire introuvables : {pages}",
            {"motif": "pages_manquantes", "anomalies_pages": anomalies},
        )


__all__ = ["PrepopulationWorker", "PrepopulationError"]
