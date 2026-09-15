"""Tests unitaires du connecteur OCR Mistral.

Le transport HTTP est simule par httpx.MockTransport : aucun appel reseau. Le
connecteur passe deux appels par page — /v1/ocr pour le markdown, puis
/v1/chat/completions pour en extraire les champs — donc le faux transport
route sur le chemin plutot que de compter les requetes.

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
from typing import Any, Callable, List, Optional

import httpx
import pytest

from adam_worker.connectors import connector_from_settings
from adam_worker.connectors.base import OcrConnectorError
from adam_core.schemas.cerfa_v2 import CERFA_V2_PAGE_FIELDS
from adam_worker.connectors.mistral import _CONSIGNE, MistralOcrConnector
from adam_worker.connectors.mock import MockOcrConnector

ENDPOINT = "https://mistral.test"
MARKDOWN = "| Nom | MARTIN |\n| --- | --- |"
DIMENSIONS = {"dpi": 300, "width": 2480, "height": 3508}


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


def _routeur(
    annotations: Callable[[int], Any],
    markdown: str = MARKDOWN,
    journal: Optional[List[httpx.Request]] = None,
) -> Callable[[httpx.Request], httpx.Response]:
    """Faux endpoint : /v1/ocr rend du markdown, /v1/chat/completions annote.

    `annotations` recoit le rang de la page soumise (1 pour la premiere page
    porteuse de champs, 2 pour la suivante...) et rend l'objet d'annotation,
    ou None pour une reponse sans contenu.
    """
    soumises = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if journal is not None:
            journal.append(request)
        if request.url.path.endswith("/v1/ocr"):
            soumises["n"] += 1
            return httpx.Response(
                200,
                json={"pages": [{"index": 0, "markdown": markdown, "dimensions": DIMENSIONS}]},
            )
        annotation = annotations(soumises["n"])
        contenu = None if annotation is None else json.dumps(annotation)
        return httpx.Response(200, json={"choices": [{"message": {"content": contenu}}]})

    return handler


# -- Cas nominal ------------------------------------------------------------


def test_extract_rend_un_document_conforme(tmp_path: Path) -> None:
    """CA-1/CA-2 : ids pointes, types wire respectes, sections groupees."""

    def annotations(page: int) -> Any:
        if page == 1:
            return {
                "deposant.nom_naissance": "MARTIN",
                "deposant.date_naissance": "1980-01-02",
                "coordonnees_personnelles.escalier": 2,
                "certification.signature_deposant": True,
                "cle.inventee": "ignoree",
            }
        # Page 2 : annotation regroupee par section, que le connecteur aplatit.
        return {"situation_familiale": {"situation_familiale.celibataire": False}}

    requetes: List[httpx.Request] = []
    doc = asyncio.run(_connector(_routeur(annotations, journal=requetes)).extract(_images(tmp_path, 2)))

    assert doc is not None
    assert doc.smartdoc_version == "0.3"
    assert doc.page_count == 2
    # Deux pages porteuses de champs, deux appels chacune.
    assert len(requetes) == 4

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
    # Les dimensions viennent de l'OCR, la completion n'en rend pas.
    assert doc.pages[0].width == 2480 and doc.pages[0].height == 3508


def test_les_deux_appels_portent_image_puis_schema(tmp_path: Path) -> None:
    """L'image part a l'OCR, le json_schema plat part en response_format."""
    requetes: List[httpx.Request] = []
    handler = _routeur(lambda _: {"deposant.prenoms": "Jean"}, journal=requetes)
    asyncio.run(_connector(handler).extract(_images(tmp_path, 1)))

    ocr, annotation = requetes
    assert str(ocr.url) == f"{ENDPOINT}/v1/ocr"
    assert ocr.headers.get("Authorization") == "Bearer cle-test"
    corps_ocr = json.loads(ocr.content)
    assert corps_ocr["document"]["image_url"].startswith("data:image/png;base64,")
    # L'annotation n'est plus deleguee a l'endpoint OCR.
    assert "document_annotation_format" not in corps_ocr

    assert str(annotation.url) == f"{ENDPOINT}/v1/chat/completions"
    corps = json.loads(annotation.content)
    assert corps["model"] == "mistral-medium-latest"
    assert corps["temperature"] == 0
    assert [m["role"] for m in corps["messages"]] == ["system", "user"]
    assert corps["messages"][0]["content"] == _CONSIGNE
    assert corps["messages"][-1]["content"] == MARKDOWN
    schema = corps["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == set(CERFA_V2_PAGE_FIELDS[1])


def test_pages_sans_schema_ne_sont_pas_soumises(tmp_path: Path) -> None:
    """Le CERFA n'a de champs qu'en pages 1, 2, 6 et 10 : 4 pages sur 10."""
    requetes: List[httpx.Request] = []
    handler = _routeur(lambda _: {"deposant.prenoms": "Jean"}, journal=requetes)
    doc = asyncio.run(_connector(handler).extract(_images(tmp_path, 10)))

    assert len(requetes) == 2 * len(CERFA_V2_PAGE_FIELDS)
    assert doc is not None
    assert doc.page_count == 10
    assert [p.page_number for p in doc.pages] == sorted(CERFA_V2_PAGE_FIELDS)


def test_page_sans_texte_economise_l_annotation(tmp_path: Path) -> None:
    """Un OCR muet n'a rien a faire annoter : le second appel n'a pas lieu."""
    requetes: List[httpx.Request] = []
    handler = _routeur(lambda _: {"deposant.prenoms": "Jean"}, markdown="   ", journal=requetes)
    doc = asyncio.run(_connector(handler).extract(_images(tmp_path, 1)))

    assert [r.url.path for r in requetes] == ["/v1/ocr"]
    assert doc is None


def test_la_consigne_interdit_le_report_entre_champs() -> None:
    """Sur un CERFA reel, une seule date de rubrique avait renseigne les cinq
    champs de date de la section, cases decochees comprises. Le json_schema ne
    sait pas exprimer cette dependance : seule la consigne le peut."""
    assert "Ne reporte jamais la valeur d'un champ dans un autre" in _CONSIGNE
    assert "les champs qui en dependent restent null" in _CONSIGNE
    assert "Ne concatene jamais plusieurs lignes" in _CONSIGNE
    # Page 10 vide, pied de page "300 bdf 1947 - dircom - 30/04/2020" : le
    # modele en avait tire date_octroi=1947-04-30 et capital_emprunte=300.
    assert "mentions d'impression ne sont pas des donnees saisies" in _CONSIGNE
    assert "rend null pour tous ses champs" in _CONSIGNE


# -- Absence de resultat (CA-3, cas nominal) --------------------------------


def test_rien_detecte_rend_none(tmp_path: Path) -> None:
    handler = _routeur(lambda _: {"deposant.nom_naissance": None, "deposant.nom_usage": ""})
    assert asyncio.run(_connector(handler).extract(_images(tmp_path, 1))) is None


def test_annotation_absente_rend_none(tmp_path: Path) -> None:
    assert asyncio.run(_connector(_routeur(lambda _: None)).extract(_images(tmp_path, 1))) is None


def test_aucune_image_rend_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("aucun appel attendu")

    assert asyncio.run(_connector(handler).extract([])) is None


# -- Echecs techniques (CA-3, OcrConnectorError) ----------------------------


def test_erreur_reseau_epuise_les_reprises(tmp_path: Path, monkeypatch) -> None:
    attempts: List[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        raise httpx.ConnectError("refus de connexion")

    monkeypatch.setattr("adam_worker.connectors.mistral._BACKOFF_SECONDS", 0.0)
    with pytest.raises(OcrConnectorError, match="injoignable"):
        asyncio.run(_connector(handler).extract(_images(tmp_path, 1)))
    assert len(attempts) == 3


def test_statut_4xx_ne_se_rejoue_pas(tmp_path: Path) -> None:
    attempts: List[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(422, json={"detail": "schema refuse"})

    with pytest.raises(OcrConnectorError, match="statut 422"):
        asyncio.run(_connector(handler).extract(_images(tmp_path, 1)))
    assert len(attempts) == 1


def test_le_4xx_nomme_la_route_et_le_motif(tmp_path: Path) -> None:
    """Le corps porte le diagnostic : un 404 nu ne se distingue pas d'un autre."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/v1/ocr"):
            return httpx.Response(
                200, json={"pages": [{"markdown": MARKDOWN, "dimensions": DIMENSIONS}]}
            )
        return httpx.Response(404, json={"message": "model does not exist for router completion"})

    with pytest.raises(OcrConnectorError, match="chat/completions.*router completion"):
        asyncio.run(_connector(handler).extract(_images(tmp_path, 1)))


def test_annotation_illisible_est_une_erreur(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/v1/ocr"):
            return httpx.Response(
                200, json={"pages": [{"markdown": MARKDOWN, "dimensions": DIMENSIONS}]}
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": "pas du json"}}]})

    with pytest.raises(OcrConnectorError, match="illisible"):
        asyncio.run(_connector(handler).extract(_images(tmp_path, 1)))


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
        mistral_annotation_model="mistral-medium-latest",
        mistral_ca_bundle="",
        ocr_timeout_seconds=30,
    )
    connector = connector_from_settings(mistral_settings)
    assert isinstance(connector, MistralOcrConnector)
    assert connector.annotation_model == "mistral-medium-latest"
