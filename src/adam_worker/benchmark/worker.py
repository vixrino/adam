"""Worker de benchmark OCR : execute les recettes de test en batch.

Une execution de test (TEST_EXECUTION, PENDING) designe une recette figee : un
lot de documents dont la verite terrain a ete etablie par des humains. Le
worker la prend, soumet chaque document au moteur OCR configure, compare sa
lecture a la verite, et n'ecrit que les ecarts.

    PENDING --(reservee, SKIP LOCKED)--> RUNNING --> COMPLETED
                                                 \\-> FAILED (message)

Ce qui le distingue de la pre-alimentation
------------------------------------------
- Il ne touche aucune donnee de production : ni ocr_result ni document_field.
  La comparaison se fait en memoire ; un benchmark ne modifie pas ce qu'il
  mesure.
- Il n'appelle pas l'API : il lit et ecrit en base directe (DepotBenchmark).

Echecs
------
- Recette non verrouillee, cle HMAC absente : FAILED avant tout appel OCR.
  Deux passages ne sont comparables que sur une recette figee, et un champ
  sensible ne peut etre juge sans sa cle d'empreinte.
- Moteur injoignable (OcrConnectorError) : FAILED. Une mesure faite sur une
  partie des documents parce que le reseau a lache n'en est pas une.
- Document que le moteur juge non conforme : pas d'arret. Il est mesure comme
  un document que le moteur n'a pas su lire (ses champs verifies comptent
  MISSING), et son id est note dans error_message.
- Document sans images de page (jamais rendu) : ecarte, sans compter dans
  la mesure, et son id est note dans error_message. Un defaut d'ingestion
  n'est pas une erreur du moteur.
- Worker arrete en plein run : l'execution, sans signe de vie depuis
  STALE_AFTER, passe en FAILED au cycle suivant d'un worker.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from adam_api.core.config import settings
from adam_core.enums.status import TestExecutionStatus, TestRecipeStatus
from adam_worker.base_worker import BaseWorker
from adam_worker.benchmark.depot import DepotBenchmark, ExecutionReservee
from adam_worker.benchmark.evaluation import (
    Agregat,
    evaluer_document,
    fusionner_histogrammes,
)
from adam_worker.connectors import connector_from_settings
from adam_worker.connectors.base import BaseOcrConnector, DocumentNonConforme
from adam_worker.connectors.modele import ModeleDocument
from adam_worker.prepopulation.poller import default_pages_dir

#: Execution RUNNING sans progres depuis ce delai : son worker est mort. Le
#: signe de vie est ecrit a chaque document, et un CERFA coute une trentaine
#: d'appels : la marge couvre un document lent sans tuer une execution vivante.
STALE_AFTER = timedelta(hours=2)


class EchecExecution(Exception):
    """Echec qui met l'execution en FAILED, avec un message lisible."""


class TestExecutionWorker(BaseWorker):
    """Execute les recettes de test OCR en attente."""

    __test__ = False  # prefixe Test* : pytest tenterait de la collecter
    poll_interval_seconds = 10.0

    def __init__(
        self,
        depot: Optional[Any] = None,
        connector: Optional[BaseOcrConnector] = None,
        *,
        pvc_root: Optional[Path] = None,
        pages_dir: Callable[[int], Path] = default_pages_dir,
        cle_hmac: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.depot = depot or DepotBenchmark()
        self.connector = connector or connector_from_settings(settings)
        self.pvc_root = pvc_root or Path(settings.pvc_mount_path)
        self.pages_dir = pages_dir
        self.cle_hmac = settings.comparison_hmac_key if cle_hmac is None else cle_hmac

    # -- Boucle -------------------------------------------------------------

    async def poll(self) -> None:
        bloquees = await self.depot.echouer_bloquees(STALE_AFTER)
        if bloquees:
            self.logger.warning("%s execution(s) interrompue(s) passee(s) en FAILED", bloquees)

        execution = await self.depot.reserver_execution(self.connector.name, self._modele_ocr())
        if execution is None:
            self.logger.debug("aucune execution de test en attente")
            return

        self.logger.info(
            "execution de test demarree [execution_id=%s recette=%s documents=%s]",
            execution.id,
            execution.recipe_id,
            len(execution.document_ids),
        )
        try:
            await self._executer(execution)
        except EchecExecution as exc:
            self.logger.error("execution %s en FAILED : %s", execution.id, exc)
            await self.depot.terminer(execution.id, TestExecutionStatus.FAILED, message=str(exc))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.logger.exception("execution %s : echec inattendu", execution.id)
            await self.depot.terminer(
                execution.id,
                TestExecutionStatus.FAILED,
                message=f"echec inattendu, voir les logs du worker ({type(exc).__name__})",
            )

    def _modele_ocr(self) -> Optional[str]:
        """Identifiant du moteur, copie sur l'execution : modele OCR et, pour
        Mistral, modele d'annotation — les deux font la lecture."""
        modeles = [
            getattr(self.connector, attribut, None) for attribut in ("model", "annotation_model")
        ]
        noms = [str(m) for m in modeles if m]
        return " + ".join(noms) or None

    # -- Execution ----------------------------------------------------------

    async def _executer(self, execution: ExecutionReservee) -> None:
        if execution.recipe_status != TestRecipeStatus.LOCKED.value:
            raise EchecExecution(
                f"recette {execution.recipe_id} non verrouillee ({execution.recipe_status}) : "
                "deux passages ne sont comparables que sur une recette figee"
            )
        if not self.cle_hmac:
            raise EchecExecution(
                "COMPARISON_HMAC_KEY absente : les champs sensibles ne peuvent etre juges"
            )

        modele = ModeleDocument.depuis_schema(await self.depot.schema(execution.schema_id))
        documents = await self.depot.documents(execution.document_ids)
        if not documents:
            raise EchecExecution(f"recette {execution.recipe_id} sans document existant")

        histogramme: Dict[str, Dict[str, List[int]]] = {}
        agregats: Dict[int, Agregat] = {}
        non_conformes: List[int] = []
        sans_images: List[int] = []

        for document_id, file_id in documents:
            images = self._images(file_id)
            if not images:
                # Pages jamais rendues : c'est un defaut d'ingestion, pas une
                # lecture ratee. Le compter MISSING imputerait au moteur une
                # erreur qui n'est pas la sienne.
                sans_images.append(document_id)
                continue
            appels_avant = int(getattr(self.connector, "appels", 0))
            try:
                ocr = await self.connector.extract(images, modele)
            except DocumentNonConforme:
                # Le moteur n'a pas su lire ce document comme le formulaire :
                # c'est une lecture ratee, mesuree comme telle.
                ocr = None
                non_conformes.append(document_id)
            except Exception as exc:
                raise EchecExecution(
                    f"moteur OCR en echec sur le document {document_id} : {exc}"
                ) from exc
            appels = int(getattr(self.connector, "appels", 0)) - appels_avant

            resultat = evaluer_document(
                await self.depot.verite(document_id), ocr, execution.id, self.cle_hmac
            )
            await self.depot.enregistrer_document(
                execution.id,
                resultat.ecarts,
                {
                    "documents_compared": 1,
                    "fields_compared": resultat.fields_compared,
                    "fields_human_verified": resultat.fields_human_verified,
                    "diff_count": len(resultat.ecarts),
                    "unexpected_count": resultat.unexpected_count,
                    "ocr_calls_made": appels,
                    "pages_processed": len(images),
                },
            )
            fusionner_histogrammes(histogramme, resultat.histogramme)
            for field_spec_id, agregat in resultat.agregats.items():
                cumul = agregats.setdefault(field_spec_id, Agregat(agregat.field_key))
                cumul.compared += agregat.compared
                cumul.diff_count += agregat.diff_count
            self.logger.info(
                "document compare [execution_id=%s document_id=%s verifies=%s ecarts=%s]",
                execution.id,
                document_id,
                resultat.fields_human_verified,
                len(resultat.ecarts),
            )

        constats = []
        if non_conformes:
            constats.append(f"documents juges non conformes par le moteur : {non_conformes}")
        if sans_images:
            constats.append(f"documents ecartes, images de page absentes : {sans_images}")
        message = " ; ".join(constats) or None
        await self.depot.terminer(
            execution.id,
            TestExecutionStatus.COMPLETED,
            histogramme=histogramme,
            agregats=agregats,
            message=message,
        )
        self.logger.info(
            "execution de test terminee [execution_id=%s documents=%s non_conformes=%s "
            "sans_images=%s]",
            execution.id,
            len(documents),
            len(non_conformes),
            len(sans_images),
        )

    def _images(self, file_id: int) -> List[Path]:
        """Images de page deja rendues par l'ingestion, dans l'ordre des noms."""
        dossier = self.pvc_root / self.pages_dir(file_id)
        return sorted(dossier.glob("*.png")) if dossier.is_dir() else []
