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

Confidentialite des logs
------------------------
Aucune valeur de champ n'est loguee, jamais. Les documents traites contiennent
des IBAN et des NIR ; les logs de ce worker ne portent que des identifiants et
des comptages, dont le nombre de champs detectes, qui suffit au diagnostic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from sqlalchemy import func, literal, select, update
from sqlalchemy.dialects.postgresql import JSONB

from adam_api.core.config import API_PREFIX, settings
from adam_core.db.session import get_async_session
from adam_core.enums.status import DocumentStatus
from adam_core.models import Document
from adam_core.schemas.interface_contract import SmartdocDocument
from adam_worker.base_worker import BaseWorker
from adam_worker.connectors import connector_from_settings
from adam_worker.connectors.base import (
    BaseOcrConnector,
    DocumentNonConforme,
    OcrConnectorError,
)
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


#: Adresses d'ecoute qui ne designent aucun hote joignable. `0.0.0.0` et `::`
#: signifient "toutes les interfaces locales" : elles disent a un serveur ou se
#: mettre, pas a un client ou aller.
#: nosec B104 : bandit y voit une ecoute sur toutes les interfaces, mais rien
#: n'ecoute ici. Ces valeurs sont reconnues pour etre remplacees par 127.0.0.1
#: dans _api_origin, ce qui est precisement l'inverse d'un bind.
_WILDCARD_HOSTS = {"0.0.0.0", "::", "[::]", ""}  # nosec B104


def _api_origin() -> str:
    """Origine HTTP de l'API, telle qu'un client doit la composer.

    api_host est l'adresse d'ECOUTE de l'API. La reutiliser telle quelle pour un
    appel sortant marche tant qu'elle vaut un hote reel, et casse des qu'elle
    vaut le joker d'ecoute : le worker tente alors une connexion vers 0.0.0.0,
    que la pile reseau refuse — ECONNREFUSED sous Windows, comportement variable
    ailleurs.

    Le joker est donc rabattu sur localhost, qui est ce qu'il designe du point de
    vue d'un processus tournant sur la meme machine. Un deploiement ou l'API vit
    ailleurs renseigne api_host avec son nom d'hote, et rien ne change ici.
    """
    host = settings.api_host.strip()
    if host in _WILDCARD_HOSTS:
        host = "127.0.0.1"
    return f"http://{host}:{settings.api_port}"


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
        api_client: Optional[ApiClient] = None,
        *,
        batch_size: int = _BATCH_SIZE,
        pvc_root: Optional[Path] = None,
        poll_interval_seconds: Optional[float] = None,
        pages_dir: Callable[[int], Path] = default_pages_dir,
    ) -> None:
        super().__init__()
        self.connector = connector or connector_from_settings(settings)
        self.api_client = api_client or ApiClient(
            # API_PREFIX est celui que main.py monte : sans lui, chaque appel
            # part en 404, que le worker traduirait en documents ERROR sans
            # que la vraie cause apparaisse nulle part.
            base_url=f"{_api_origin()}{API_PREFIX}",
            # Sans cette cle, aucun en-tete d'authentification n'est emis et
            # get_caller rejette l'appel en 401 : le worker mettait alors CHAQUE
            # document en ERROR avec « schema injoignable », en production
            # uniquement — le script de test surcharge get_caller par un
            # ServiceCaller et ne voyait donc rien.
            api_key=settings.internal_api_key,
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

        # En DEBUG : chaque document du lot emet ensuite sa propre ligne, avec le
        # detail qui compte. Annoncer le decompte n'ajoutait rien devant N lignes
        # qui le disent.
        self.logger.debug("%s document(s) INGESTED a pre-alimenter", len(candidates))
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
                await self._set_error(document_id, {"message": str(exc), **exc.details})
            except Exception:  # pylint: disable=broad-exception-caught
                # Filet : un imprevu ne doit pas interrompre le lot.
                self.logger.exception("echec inattendu [document_id=%s]", document_id)
                await self._set_error(
                    document_id, {"message": "echec inattendu, voir les logs du worker"}
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

    async def _process_one(self, document_id: int) -> None:
        dataset_id, file_id = await self._load_context(document_id)
        images = self._page_images(file_id)

        ocr = await self._run_ocr(images, document_id)
        _controle_pages(ocr)
        await self._reordonner_images(document_id, images, ocr)
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
                    select(Document.dataset_id, Document.file_id).where(Document.id == document_id)
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

    async def _load_field_specs(self, dataset_id: int, document_id: int) -> List[Dict[str, Any]]:
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
        """Ajoute des cles a metadata sans ecraser les autres (concatenation JSONB)."""
        values: Dict[str, Any] = {
            "metadata_": func.coalesce(Document.metadata_, literal({}, JSONB)).op("||")(
                literal(cles, JSONB)
            )
        }
        if status is not None:
            values["status"] = status.value
        async with get_async_session() as db:
            await db.execute(update(Document).where(Document.id == document_id).values(**values))

    async def _reordonner_images(
        self,
        document_id: int,
        images: Sequence[Path],
        ocr: Optional[SmartdocDocument],
    ) -> None:
        """Renomme les images pour que l'image N porte la page N du formulaire.

        Les noms cibles sont ceux des images existantes : l'image de rang r
        prend le nom de l'image de rang p, ou p est la page qu'elle porte. Le
        worker n'a ainsi pas a connaitre la convention de nommage du rendu.
        """
        if ocr is None:
            return
        permutation = _permutation(ocr.metadata.get("ordre_pages"), len(images))
        if not permutation:
            return
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

        deplacees = [{"page": page, "rang_origine": rang} for rang, page in permutation.items()]
        self.logger.warning(
            "images de page remises dans l'ordre du formulaire [document_id=%s] : %s",
            document_id,
            deplacees,
        )
        await self._update_metadata(document_id, {"pages_reordonnees": deplacees})


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
