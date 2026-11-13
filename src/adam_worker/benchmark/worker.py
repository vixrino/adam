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

import hashlib
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from adam_api.core.config import settings
from adam_core.benchmark.recette import ConfigOcr, config_ocr
from adam_core.benchmark.schema import empreinte_schema  # reexporte : tests, scripts
from adam_core.benchmark.verite import empreinte_document, empreinte_verite
from adam_core.enums.status import TestExecutionStatus, TestRecipeStatus
from adam_worker.base_worker import BaseWorker
from adam_worker.benchmark.comparateur import COMPARATEUR_VERSION
from adam_worker.benchmark.depot import DepotBenchmark, ExecutionReservee
from adam_worker.benchmark.evaluation import (
    Agregat,
    evaluer_document,
    fusionner_histogrammes,
)
from adam_worker.connectors import connector_from_settings, connector_pour_recette
from adam_worker.connectors.base import BaseOcrConnector, DocumentNonConforme
from adam_worker.connectors.modele import ModeleDocument
from adam_worker.prepopulation.poller import default_pages_dir

#: Execution RUNNING sans progres depuis ce delai : son worker est mort. Le
#: signe de vie est ecrit a chaque document, et un CERFA coute une trentaine
#: d'appels : la marge couvre un document lent sans tuer une execution vivante.
STALE_AFTER = timedelta(hours=2)


class EchecExecution(Exception):
    """Echec qui met l'execution en FAILED, avec un message lisible."""


class ExecutionInterrompue(Exception):
    """L'execution n'est plus RUNNING (annulee depuis l'API, ou passee FAILED
    par echouer_bloquees) : on s'arrete sans la clore, elle l'est deja."""


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
        fabrique: Optional[
            Callable[[ConfigOcr, BaseOcrConnector], Tuple[BaseOcrConnector, bool]]
        ] = None,
    ) -> None:
        super().__init__()
        self.depot = depot or DepotBenchmark()
        #: Le moteur du .env, pour les recettes qui n'en precisent pas.
        self.connector = connector or connector_from_settings(settings)
        #: Construit le moteur d'une recette ; injectable pour les tests.
        self.fabrique = fabrique or (
            lambda config, defaut: connector_pour_recette(config, settings, defaut)
        )
        self.pvc_root = pvc_root or Path(settings.pvc_mount_path)
        self.pages_dir = pages_dir
        self.cle_hmac = settings.comparison_hmac_key if cle_hmac is None else cle_hmac

    # -- Boucle -------------------------------------------------------------

    async def poll(self) -> None:
        bloquees = await self.depot.echouer_bloquees(STALE_AFTER)
        if bloquees:
            self.logger.warning("%s execution(s) interrompue(s) passee(s) en FAILED", bloquees)

        execution = await self.depot.reserver_execution()
        if execution is None:
            self.logger.debug("aucune execution de test en attente")
            return
        try:
            connecteur, a_fermer = self.fabrique(config_ocr(execution.config), self.connector)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Moteur de la recette inconstructible (cle absente...) : l'execution
            # echoue proprement au lieu de rester RUNNING.
            self.logger.error("execution %s : moteur OCR inconstructible : %s", execution.id, exc)
            await self.depot.terminer(
                execution.id,
                TestExecutionStatus.FAILED,
                message=f"moteur OCR de la recette inconstructible : {exc}",
            )
            return

        self.logger.info(
            "execution de test demarree [execution_id=%s recette=%s documents=%s]",
            execution.id,
            execution.recipe_id,
            len(execution.document_ids),
        )
        try:
            # Dans le try : si la note echoue, le moteur est quand meme ferme
            # et l'execution passe en FAILED au lieu de rester RUNNING.
            await self.depot.noter_moteur(
                execution.id, connecteur.name.upper(), _modele_ocr(connecteur)
            )
            await self._executer(execution, connecteur)
        except ExecutionInterrompue:
            self.logger.info("execution de test interrompue [execution_id=%s]", execution.id)
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
        finally:
            if a_fermer and hasattr(connecteur, "aclose"):
                await connecteur.aclose()

    # -- Execution ----------------------------------------------------------

    async def _executer(self, execution: ExecutionReservee, connecteur: BaseOcrConnector) -> None:
        if execution.recipe_status != TestRecipeStatus.LOCKED.value:
            raise EchecExecution(
                f"recette {execution.recipe_id} non verrouillee ({execution.recipe_status}) : "
                "deux passages ne sont comparables que sur une recette figee"
            )
        if not self.cle_hmac:
            raise EchecExecution(
                "COMPARISON_HMAC_KEY absente : les champs sensibles ne peuvent etre juges"
            )

        schema = await self.depot.schema(execution.schema_id)
        empreinte = empreinte_schema(schema)
        await self.depot.identifier(execution.id, COMPARATEUR_VERSION, empreinte)
        modele = ModeleDocument.depuis_schema(schema)
        documents = await self.depot.documents(execution.document_ids)
        if not documents:
            raise EchecExecution(f"recette {execution.recipe_id} sans document existant")
        absents = sorted(set(execution.document_ids) - {d for d, _ in documents})
        if absents:
            # Comptes traites d'emblee : sans cela la progression, rapportee
            # aux documents de la recette, n'atteindrait jamais le total.
            await self.depot.enregistrer_document(
                execution.id, [], {"documents_traites": len(absents)}
            )

        histogramme: Dict[str, Dict[str, List[int]]] = {}
        agregats: Dict[int, Agregat] = {}
        non_conformes: List[int] = []
        sans_images: List[int] = []
        #: Empreinte de la verite de chaque document juge.
        verites: Dict[int, str] = {}

        for document_id, file_id in documents:
            # Entre deux documents : un document entame va au bout, ses appels
            # OCR sont deja payes.
            if await self.depot.interrompue(execution.id):
                raise ExecutionInterrompue()
            images = self._images(file_id)
            if not images:
                # Pages jamais rendues : c'est un defaut d'ingestion, pas une
                # lecture ratee. Le compter MISSING imputerait au moteur une
                # erreur qui n'est pas la sienne.
                sans_images.append(document_id)
                await self.depot.enregistrer_document(execution.id, [], {"documents_traites": 1})
                continue
            appels_avant = int(getattr(connecteur, "appels", 0))
            try:
                ocr = await connecteur.extract(images, modele)
            except DocumentNonConforme:
                # Le moteur n'a pas su lire ce document comme le formulaire :
                # c'est une lecture ratee, mesuree comme telle.
                ocr = None
                non_conformes.append(document_id)
            except Exception as exc:
                raise EchecExecution(
                    f"moteur OCR en echec sur le document {document_id} : {exc}"
                ) from exc
            appels = int(getattr(connecteur, "appels", 0)) - appels_avant

            verite = await self.depot.verite(document_id)
            verites[document_id] = empreinte_document(
                (c.field_spec_id, c.group_id, c.attendu) for c in verite if c.verifie
            )
            resultat = evaluer_document(verite, ocr, execution.id, self.cle_hmac)
            await self.depot.enregistrer_document(
                execution.id,
                resultat.ecarts,
                {
                    "documents_traites": 1,
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
                if field_spec_id in agregats:
                    agregats[field_spec_id].ajouter(agregat)
                else:
                    agregats[field_spec_id] = agregat
            self.logger.info(
                "document compare [execution_id=%s document_id=%s verifies=%s ecarts=%s]",
                execution.id,
                document_id,
                resultat.fields_human_verified,
                len(resultat.ecarts),
            )

        constats = []
        if absents:
            # Supprimes depuis l'export (droit a l'effacement...) : le passage
            # porte sur moins de documents que la recette, et doit le dire.
            constats.append(f"documents de la recette absents de la base : {absents}")
        if execution.schema_hash_export and execution.schema_hash_export != empreinte:
            # Le schema a change depuis l'export : la verite et la lecture ne
            # portent plus tout a fait sur les memes champs qu'a l'export.
            constats.append("schema du dataset modifie depuis l'export")
        if execution.verite_export is not None:
            # Une valeur corrigee depuis l'export : le score de ce passage ne
            # se compare plus a celui d'un passage d'avant la correction.
            modifies = sorted(
                d for d, e in verites.items() if execution.verite_export.get(str(d)) != e
            )
            if modifies:
                constats.append(f"verite humaine modifiee depuis l'export : documents {modifies}")
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
            verite_hash=empreinte_verite(verites),
        )
        self.logger.info("execution de test terminee [execution_id=%s]", execution.id)

    def _images(self, file_id: int) -> List[Path]:
        """Images de page deja rendues par l'ingestion, dans l'ordre des noms."""
        dossier = self.pvc_root / self.pages_dir(file_id)
        return sorted(dossier.glob("*.png")) if dossier.is_dir() else []


def _modele_ocr(connecteur: BaseOcrConnector) -> Optional[str]:
    """Identifiant du moteur, copie sur l'execution : modele OCR et, pour
    Mistral, modele d'annotation — les deux font la lecture."""
    modeles = [getattr(connecteur, attribut, None) for attribut in ("model", "annotation_model")]
    noms = [str(m) for m in modeles if m]
    consigne = getattr(connecteur, "consigne", None)
    if consigne:
        # La consigne change la lecture : son empreinte dit si deux executions
        # aux scores differents ont lu avec le meme prompt.
        noms.append("consigne " + hashlib.sha256(str(consigne).encode()).hexdigest()[:8])
    return " + ".join(noms) or None
