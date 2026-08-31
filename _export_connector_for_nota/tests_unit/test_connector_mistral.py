"""Tests unitaires du connecteur OCR Mistral.

Le transport HTTP est simule par httpx.MockTransport : aucun appel reseau.
Les criteres d'acceptation du ticket T5 couverts ici :

    CA-1  extract rend un SmartdocDocument valide
    CA-2  les KVPair portent les cles pointees du schema
    CA-3  injoignable -> OcrConnectorError ; rien detecte -> None
    CA-5  cle et endpoint exiges de la configuration, jamais en dur
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List

import httpx
import pytest

from nota_worker.connectors import connector_from_settings
from nota_worker.connectors.base import OcrConnectorError
from nota_worker.connectors.cerfa_schema import CERFA_V2_PAGE_FIELDS
from nota_worker.connectors.mistral import MistralOcrConnector
from nota_worker.connectors.mock import MockOcrConnector

ENDPOINT = "https://mistral.test"


def _connector(handler: Callable[[httpx.Request], httpx.Response]) -> MistralOcrConnector:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer cle-test"},
    )
    return MistralOcrConnector(api_key="cle-test", endpoint=ENDPOINT, client=client)


def _images(tmp_path: Path, count: int) -> List[Path]:
    paths = []
    for i in range(1, count + 1):
        p = tmp_path / f"page_{i:03d}.png"
        p.write_bytes(b"fausse-image")
        paths.append(p)
    return paths


def _ocr_response(annotation: Any) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "pages": [{"index": 0, "dimensions": {"dpi": 300, "width": 2480, "height": 3508}}],
            "document_annotation": json.dumps(annotation) if annotation is not None else None,
        },
    )


# -- Cas nominal ------------------------------------------------------------


def test_extract_rend_un_document_conforme(tmp_path: Path) -> None:
    """CA-1/CA-2 : ids pointes, types wire respectes, sections groupees."""
    requests: List[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = len(requests)
        if page == 1:
            return _ocr_response(
                {
                    "deposant.nom_naissance": "MARTIN",
                    "deposant.date_naissance": "1980-01-02",
                    "coordonnees_personnelles.escalier": 2,
                    "certification.signature_deposant": True,
                    "cle.inventee": "ignoree",
                }
            )
        # Page 2 : annotation regroupee par section, que le connecteur aplatit.
        return _ocr_response({"situation_familiale": {"situation_familiale.celibataire": False}})

    connector = _connector(handler)
    doc = asyncio.run(connector.extract(_images(tmp_path, 2)))

    assert doc is not None
    assert doc.smartdoc_version == "0.3"
    assert doc.page_count == 2
    assert len(requests) == 2

    by_id = {kv.id: kv for _, _, kv in doc.iter_kv_pairs()}
    assert by_id["deposant.nom_naissance"].value.type == "text"
    assert by_id["deposant.nom_naissance"].extracted_value == "MARTIN"
    assert by_id["deposant.date_naissance"].value.type == "date"
    assert by_id["coordonnees_personnelles.escalier"].value.type == "number"
    assert by_id["certification.signature_deposant"].value.type == "boolean"
    # False est une detection (case vue non cochee), pas une absence.
    assert by_id["situation_familiale.celibataire"].extracted_value == "false"
    # La cle inventee par le modele n'existe pas dans le document.
    assert "cle.inventee" not in by_id
    # Un champ attendu mais non rendu existe, sans valeur.
    assert by_id["deposant.nom_usage"].value is None
    # Les sections reprennent le premier segment des cles.
    sections = {s.id for _, s, _ in doc.iter_kv_pairs()}
    assert "deposant" in sections and "situation_familiale" in sections


def test_requete_porte_schema_et_image(tmp_path: Path) -> None:
    """L'appel contient le json_schema plat de la page et l'image en data URI."""
    captured: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return _ocr_response({"deposant.prenoms": "Jean"})

    connector = _connector(handler)
    asyncio.run(connector.extract(_images(tmp_path, 1)))

    assert captured["url"] == f"{ENDPOINT}/v1/ocr"
    assert captured["auth"] == "Bearer cle-test"
    body = captured["body"]
    assert body["document"]["image_url"].startswith("data:image/png;base64,")
    schema = body["document_annotation_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == set(CERFA_V2_PAGE_FIELDS[1])


def test_pages_sans_schema_ne_sont_pas_soumises(tmp_path: Path) -> None:
    """Le CERFA n'a de champs qu'en pages 1, 2, 6 et 10 : 4 appels pour 10 pages."""
    calls: List[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _ocr_response({"deposant.prenoms": "Jean"})

    connector = _connector(handler)
    doc = asyncio.run(connector.extract(_images(tmp_path, 10)))

    assert len(calls) == len(CERFA_V2_PAGE_FIELDS)
    assert doc is not None
    assert doc.page_count == 10
    assert [p.page_number for p in doc.pages] == sorted(CERFA_V2_PAGE_FIELDS)


# -- Absence de resultat (CA-3, cas nominal) --------------------------------


def test_rien_detecte_rend_none(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ocr_response({"deposant.nom_naissance": None, "deposant.nom_usage": ""})

    connector = _connector(handler)
    assert asyncio.run(connector.extract(_images(tmp_path, 1))) is None


def test_annotation_absente_rend_none(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _ocr_response(None)

    connector = _connector(handler)
    assert asyncio.run(connector.extract(_images(tmp_path, 1))) is None


def test_aucune_image_rend_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("aucun appel attendu")

    connector = _connector(handler)
    assert asyncio.run(connector.extract([])) is None


# -- Echecs techniques (CA-3, OcrConnectorError) ----------------------------


def test_erreur_reseau_epuise_les_reprises(tmp_path: Path, monkeypatch) -> None:
    attempts: List[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        raise httpx.ConnectError("refus de connexion")

    monkeypatch.setattr("nota_worker.connectors.mistral._BACKOFF_SECONDS", 0.0)
    connector = _connector(handler)
    with pytest.raises(OcrConnectorError, match="injoignable"):
        asyncio.run(connector.extract(_images(tmp_path, 1)))
    assert len(attempts) == 3


def test_statut_4xx_ne_se_rejoue_pas(tmp_path: Path) -> None:
    attempts: List[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(422, json={"detail": "schema refuse"})

    connector = _connector(handler)
    with pytest.raises(OcrConnectorError, match="statut 422"):
        asyncio.run(connector.extract(_images(tmp_path, 1)))
    assert len(attempts) == 1


def test_annotation_illisible_est_une_erreur(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"pages": [], "document_annotation": "pas du json"})

    connector = _connector(handler)
    with pytest.raises(OcrConnectorError, match="illisible"):
        asyncio.run(connector.extract(_images(tmp_path, 1)))


# -- Configuration (CA-4/CA-5) ----------------------------------------------


def test_cle_et_endpoint_obligatoires() -> None:
    with pytest.raises(ValueError, match="MISTRAL_API_KEY"):
        MistralOcrConnector(api_key="", endpoint=ENDPOINT)
    with pytest.raises(ValueError, match="MISTRAL_OCR_ENDPOINT"):
        MistralOcrConnector(api_key="cle", endpoint="")


def test_factory_choisit_le_connecteur_selon_la_configuration() -> None:
    """CA-4 : le passage du mock a Mistral est un changement de configuration."""
    mock_settings = SimpleNamespace(ocr_mock_enabled=True, ocr_mock_confidence=0.9)
    assert isinstance(connector_from_settings(mock_settings), MockOcrConnector)

    mistral_settings = SimpleNamespace(
        ocr_mock_enabled=False,
        mistral_api_key="cle",
        mistral_ocr_endpoint=ENDPOINT,
        mistral_ocr_model="mistral-ocr-latest",
        mistral_ca_bundle="",
        ocr_timeout_seconds=30,
    )
    assert isinstance(connector_from_settings(mistral_settings), MistralOcrConnector)
