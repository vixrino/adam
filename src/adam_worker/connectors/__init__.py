"""Connecteurs OCR : interface commune et implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from adam_worker.connectors.base import BaseOcrConnector

if TYPE_CHECKING:
    # Sous TYPE_CHECKING seulement : annoter le parametre ne doit pas faire
    # dependre le simple import du paquet connecteurs de toute la config API.
    from adam_api.core.config import Settings
    from adam_core.benchmark.recette import ConfigOcr


def connector_from_settings(settings: "Settings") -> BaseOcrConnector:
    """Connecteur dicte par la configuration : mock en dev, Mistral sinon.

    Les imports sont locaux pour que le simple import du paquet ne tire ni
    httpx ni le schema CERFA quand on ne construit aucun connecteur.
    """
    if settings.ocr_mock_enabled:
        from adam_worker.connectors.mock import MockOcrConnector

        return MockOcrConnector(confidence=settings.ocr_mock_confidence)

    from adam_worker.connectors.mistral import MistralOcrConnector

    return MistralOcrConnector(
        api_key=settings.mistral_api_key,
        endpoint=settings.mistral_ocr_endpoint,
        model=settings.mistral_ocr_model,
        annotation_model=settings.mistral_annotation_model,
        timeout_seconds=float(settings.ocr_timeout_seconds),
        ca_bundle=settings.mistral_ca_bundle or None,
    )


def connector_pour_recette(
    config: "ConfigOcr", settings: "Settings", defaut: BaseOcrConnector
) -> Tuple[BaseOcrConnector, bool]:
    """Le moteur d'une recette de benchmark, et s'il faut le fermer apres.

    Une recette sans moteur precise lit avec celui du worker (``defaut``,
    construit depuis le .env). Sinon, chaque champ vide reprend la valeur du
    .env : une recette qui ne change que le prompt garde le modele courant.
    """
    if not (config.provider or config.model or config.annotation_model or config.prompt):
        return defaut, False
    fournisseur = config.provider or ("MOCK" if settings.ocr_mock_enabled else "MISTRAL")
    if fournisseur == "MOCK":
        from adam_worker.connectors.mock import MockOcrConnector

        return MockOcrConnector(confidence=settings.ocr_mock_confidence), False

    from adam_worker.connectors.mistral import MistralOcrConnector

    return (
        MistralOcrConnector(
            api_key=settings.mistral_api_key,
            endpoint=settings.mistral_ocr_endpoint,
            model=config.model or settings.mistral_ocr_model,
            annotation_model=config.annotation_model or settings.mistral_annotation_model,
            timeout_seconds=float(settings.ocr_timeout_seconds),
            ca_bundle=settings.mistral_ca_bundle or None,
            consigne=config.prompt,
        ),
        True,
    )
