"""Connecteurs OCR : interface commune et implementations."""

from __future__ import annotations

from nota_worker.connectors.base import BaseOcrConnector


def connector_from_settings(settings) -> BaseOcrConnector:
    """Connecteur dicte par la configuration : mock en dev, Mistral sinon.

    Les imports sont locaux pour que le simple import du paquet ne tire ni
    httpx ni le schema CERFA quand on ne construit aucun connecteur.
    """
    if settings.ocr_mock_enabled:
        from nota_worker.connectors.mock import MockOcrConnector

        return MockOcrConnector(confidence=settings.ocr_mock_confidence)

    from nota_worker.connectors.mistral import MistralOcrConnector

    return MistralOcrConnector(
        api_key=settings.mistral_api_key,
        endpoint=settings.mistral_ocr_endpoint,
        model=settings.mistral_ocr_model,
        timeout_seconds=float(settings.ocr_timeout_seconds),
        ca_bundle=settings.mistral_ca_bundle or None,
    )
