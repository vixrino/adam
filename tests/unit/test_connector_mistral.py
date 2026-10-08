"""Tests unitaires du connecteur OCR Mistral.

Le transport HTTP est simule par httpx.MockTransport : aucun appel reseau. Le
connecteur passe jusqu'a trois appels par page — /v1/ocr pour le markdown, puis
deux /v1/chat/completions, l'un pour identifier la page du CERFA, l'autre pour
en extraire les champs — donc le faux transport route sur le chemin et sur le
nom du json_schema plutot que de compter les requetes.

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
from adam_worker.connectors.mistral import (
    _CONSIGNE,
    _IDENTIFICATION,
    MistralOcrConnector,
    _to_kv_value,
)
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
    identification: Callable[[int], Any] = lambda rang: rang,
) -> Callable[[httpx.Request], httpx.Response]:
    """Faux endpoint : /v1/ocr rend du markdown, /v1/chat/completions identifie
    la page ou l'annote selon le json_schema recu.

    `annotations` et `identification` recoivent le rang de l'image dans le PDF
    (1 pour la premiere). `identification` rend la page du CERFA reconnue — par
    defaut le rang, document dans l'ordre — et `annotations` l'objet
    d'annotation, ou None pour une reponse sans contenu.
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
        corps = json.loads(request.content)
        if corps["response_format"]["json_schema"]["name"] == _IDENTIFICATION:
            page = identification(soumises["n"])
            return httpx.Response(
                200, json={"choices": [{"message": {"content": json.dumps({"page": page})}}]}
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
                "coordonnees_personnelles.code_postal": "01500",
                "certification.signature_deposant": True,
                "cle.inventee": "ignoree",
            }
        # Page 2 : annotation regroupee par section, que le connecteur aplatit.
        return {"situation_familiale": {"situation_familiale.celibataire": False}}

    requetes: List[httpx.Request] = []
    doc = asyncio.run(
        _connector(_routeur(annotations, journal=requetes)).extract(_images(tmp_path, 2))
    )

    assert doc is not None
    assert doc.smartdoc_version == "0.3"
    assert doc.page_count == 2
    # Deux pages porteuses de champs, trois appels chacune.
    assert len(requetes) == 6

    by_id = {kv.id: kv for _, _, kv in doc.iter_kv_pairs()}
    assert by_id["deposant.nom_naissance"].value.type == "text"
    assert by_id["deposant.nom_naissance"].extracted_value == "MARTIN"
    assert by_id["deposant.date_naissance"].value.type == "date"
    # Code postal en texte : un number aurait rendu 1500.
    assert by_id["coordonnees_personnelles.code_postal"].value.type == "text"
    assert by_id["coordonnees_personnelles.code_postal"].extracted_value == "01500"
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

    ocr, _identification, annotation = requetes
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


def test_le_schema_autorise_null_sur_chaque_champ(tmp_path: Path) -> None:
    """Sans null, le mode strict oblige le modele a fabriquer une valeur.

    Sur un CERFA reel, date_octroi rendait 1947-01-01 pour un tableau vide :
    le type "string" seul interdisait la seule reponse juste.
    """
    requetes: List[httpx.Request] = []
    handler = _routeur(lambda _: {"deposant.prenoms": "Jean"}, journal=requetes)
    asyncio.run(_connector(handler).extract(_images(tmp_path, 1)))

    schema = json.loads(requetes[2].content)["response_format"]["json_schema"]["schema"]
    proprietes = schema["properties"]
    assert all("null" in p["type"] for p in proprietes.values())
    # Le type du contrat survit a cote de null, il n'est pas remplace.
    assert "boolean" in proprietes["deposant.civilite_monsieur"]["type"]
    # Strict exige que tout figure dans required : l'absence passe par null.
    assert set(schema["required"]) == set(proprietes)


def test_pages_sans_schema_ne_sont_pas_annotees(tmp_path: Path) -> None:
    """Toutes les pages passent a l'OCR et a l'identification, puisqu'une page
    a champs peut etre a n'importe quel rang ; seules les pages a champs sont
    annotees."""
    requetes: List[httpx.Request] = []
    handler = _routeur(lambda _: {"deposant.prenoms": "Jean"}, journal=requetes)
    doc = asyncio.run(_connector(handler).extract(_images(tmp_path, 12)))

    # Page 12, l'avertissement d'envoi, n'a pas de champs : OCR et
    # identification seulement.
    assert len(requetes) == 2 * 12 + len(CERFA_V2_PAGE_FIELDS)
    assert doc is not None
    assert doc.page_count == 12
    assert [p.page_number for p in doc.pages] == sorted(CERFA_V2_PAGE_FIELDS)
    # Document dans l'ordre et complet : rien a signaler.
    assert doc.metadata["anomalies_pages"] == []


# -- Identification des pages -----------------------------------------------


def _schema_annote(requete: httpx.Request) -> set:
    return set(
        json.loads(requete.content)["response_format"]["json_schema"]["schema"]["properties"]
    )


def test_pages_inversees_sont_annotees_avec_leur_propre_schema(tmp_path: Path) -> None:
    """Pages 1 et 2 scannees dans l'ordre inverse : l'image 1 porte la page 2
    et doit etre annotee avec le schema de la page 2, pas celui de son rang."""
    requetes: List[httpx.Request] = []
    handler = _routeur(
        lambda _: {"deposant.prenoms": "Jean"},
        journal=requetes,
        identification=lambda rang: {1: 2, 2: 1}[rang],
    )
    doc = asyncio.run(_connector(handler).extract(_images(tmp_path, 2)))

    annotations = [
        r
        for r in requetes
        if json.loads(r.content).get("response_format", {}).get("json_schema", {}).get("name")
        not in (None, _IDENTIFICATION)
    ]
    assert _schema_annote(annotations[0]) == set(CERFA_V2_PAGE_FIELDS[2])
    assert _schema_annote(annotations[1]) == set(CERFA_V2_PAGE_FIELDS[1])
    assert doc is not None
    assert [p.page_number for p in doc.pages] == [2, 1]
    assert doc.metadata["anomalies_pages"][:2] == [
        {"type": "page_deplacee", "rang": 1, "page_reconnue": 2},
        {"type": "page_deplacee", "rang": 2, "page_reconnue": 1},
    ]


def test_page_inattendue_n_est_pas_annotee(tmp_path: Path) -> None:
    """Une page etrangere au rang d'une page a champs est signalee, et surtout
    pas annotee avec le schema de ce rang."""
    requetes: List[httpx.Request] = []
    handler = _routeur(
        lambda _: {"deposant.prenoms": "Jean"},
        journal=requetes,
        identification=lambda rang: None if rang == 2 else rang,
    )
    doc = asyncio.run(_connector(handler).extract(_images(tmp_path, 2)))

    # Image 2 : OCR et identification, pas d'annotation.
    assert len(requetes) == 3 + 2
    assert doc is not None
    assert [p.page_number for p in doc.pages] == [1]
    anomalies = doc.metadata["anomalies_pages"]
    assert {"type": "page_inattendue", "rang": 2, "page_attendue": 2} in anomalies
    manquantes = next(a for a in anomalies if a["type"] == "pages_manquantes")
    assert manquantes["pages"] == sorted(set(CERFA_V2_PAGE_FIELDS) - {1})


def test_page_en_double_n_est_annotee_qu_une_fois(tmp_path: Path) -> None:
    """La meme page scannee deux fois : la premiere est retenue."""
    handler = _routeur(lambda _: {"deposant.prenoms": "Jean"}, identification=lambda _: 1)
    doc = asyncio.run(_connector(handler).extract(_images(tmp_path, 2)))

    assert doc is not None
    assert [p.page_number for p in doc.pages] == [1]
    assert {
        "type": "page_en_double",
        "rang": 2,
        "page_reconnue": 1,
        "rang_retenu": 1,
    } in doc.metadata["anomalies_pages"]


def test_page_hors_schema_rendue_par_le_modele_vaut_none(tmp_path: Path) -> None:
    """Un numero inconnu du schema, ou un booleen, ne doit pas choisir de schema."""
    for reponse in (13, True, "1"):
        requetes: List[httpx.Request] = []
        handler = _routeur(
            lambda _: {"deposant.prenoms": "Jean"},
            journal=requetes,
            identification=lambda _, r=reponse: r,
        )
        assert asyncio.run(_connector(handler).extract(_images(tmp_path, 1))) is None
        assert len(requetes) == 2


def test_la_consigne_d_identification_decrit_les_pages_du_schema(tmp_path: Path) -> None:
    requetes: List[httpx.Request] = []
    handler = _routeur(lambda _: {"deposant.prenoms": "Jean"}, journal=requetes)
    asyncio.run(_connector(handler).extract(_images(tmp_path, 1)))

    corps = json.loads(requetes[1].content)
    consigne = corps["messages"][0]["content"]
    assert corps["temperature"] == 0
    assert corps["messages"][-1]["content"] == MARKDOWN
    for page_number in CERFA_V2_PAGE_FIELDS:
        assert f"- page {page_number} :" in consigne
    # Les pages sans champs sont decrites aussi, par leurs rubriques imprimees.
    assert "- page 5 : Patrimoine" in consigne
    assert "Credits a la consommation" in consigne
    assert "Rends null si la page n'est aucune" in consigne


def test_la_consigne_d_identification_ecarte_le_rang() -> None:
    """Un CERFA reel est arrive pages 9 et 10 inversees, et un modele qui
    numerotait les pages dans l'ordre de reception s'y est trompe."""
    consigne = _connector(lambda _: httpx.Response(500))._consigne_identification
    assert "scanne dans le desordre" in consigne
    assert "Identifie la page par ses titres de rubrique uniquement" in consigne
    # Le pied de page "300 BdF 1947 - DIRCOM - 30/04/2020" est commun a toutes.
    assert "la meme sur toutes les pages" in consigne
    # Pages 10 et 11 : meme titre, la 11 porte en plus deux autres rubriques.
    assert "Autres prets et cautionnements" in consigne
    assert "sans elles, c'est la page 10" in consigne


def test_pages_9_et_10_inversees_comme_sur_le_cerfa_reel(tmp_path: Path) -> None:
    """Ordre reel 1..8, 10, 9, 11, 12 : chaque tableau de prets garde son schema."""
    ordre = [1, 2, 3, 4, 5, 6, 7, 8, 10, 9, 11, 12]
    requetes: List[httpx.Request] = []
    handler = _routeur(
        lambda _: {"deposant.prenoms": "Jean"},
        journal=requetes,
        identification=lambda rang: ordre[rang - 1],
    )
    doc = asyncio.run(_connector(handler).extract(_images(tmp_path, 12)))

    annotations = [
        _schema_annote(r)
        for r in requetes
        if json.loads(r.content).get("response_format", {}).get("json_schema", {}).get("name")
        not in (None, _IDENTIFICATION)
    ]
    # Rangs 9 et 10 : 9e et 10e annotations, toutes les pages 1 a 11 ayant des champs.
    assert annotations[8] == set(CERFA_V2_PAGE_FIELDS[10])
    assert annotations[9] == set(CERFA_V2_PAGE_FIELDS[9])
    assert doc is not None
    assert doc.metadata["anomalies_pages"] == [
        {"type": "page_deplacee", "rang": 9, "page_reconnue": 10},
        {"type": "page_deplacee", "rang": 10, "page_reconnue": 9},
    ]


def test_page_sans_champs_reconnue_n_est_pas_annotee(tmp_path: Path) -> None:
    """La page 12 placee en tete : reconnue et signalee, jamais annotee."""
    requetes: List[httpx.Request] = []
    handler = _routeur(
        lambda _: {"deposant.prenoms": "Jean"},
        journal=requetes,
        identification=lambda rang: {1: 12, 2: 1}[rang],
    )
    doc = asyncio.run(_connector(handler).extract(_images(tmp_path, 2)))

    # Image 1 : OCR et identification ; image 2 : les trois appels.
    assert len(requetes) == 2 + 3
    assert doc is not None
    assert [p.page_number for p in doc.pages] == [1]
    assert {"type": "page_deplacee", "rang": 1, "page_reconnue": 12} in doc.metadata[
        "anomalies_pages"
    ]


def test_la_consigne_ne_complete_pas_une_date_partielle() -> None:
    """« Depuis le : 2018 » : field_parser n'accepte que jj/mm/aaaa, et un
    modele somme de rendre une date complete inventerait 2018-01-01."""
    assert "Une date incomplete" in _CONSIGNE
    assert "ne complete jamais un jour ou un mois" in _CONSIGNE


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


def test_la_consigne_distingue_case_vide_et_reponse_par_exclusion() -> None:
    """Une case non cochee est une absence, sauf dans un groupe exclusif.

    Si « non » est coche, « oui » n'est pas indetermine : le document y repond,
    et le champ vaut false. Isolee, la meme case non cochee ne dit rien et rend
    null. Le json_schema declare des booleens independants et ne peut pas
    exprimer le groupe : seule la consigne le peut.
    """
    assert "Une case non cochee rend null" in _CONSIGNE
    assert "cocher l'une repond pour toutes" in _CONSIGNE
    assert "Si aucune n'est cochee dans le groupe, toutes rendent null" in _CONSIGNE
    # Un champ vide de sens du fait de la reponse cochee (numero de dossier
    # alors qu'il n'y a pas de dossier) suit la meme logique.
    assert "prive d'objet" in _CONSIGNE


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


def test_un_montant_sort_en_number() -> None:
    """Les montants restent des number, eux : seuls les codes en sortent."""
    spec = CERFA_V2_PAGE_FIELDS[10]["credits_consommation.montant_impaye"]
    assert _to_kv_value(2800, spec).type == "number"


def test_personnes_a_charge_ont_une_colonne_nom() -> None:
    """Sans champ pour le nom, le modele rangeait « Luna Vincent » dans
    lien_parente : le nom n'avait nulle part d'autre ou aller."""
    page_2 = CERFA_V2_PAGE_FIELDS[2]
    assert "personnes_a_charge.nom_prenom" in page_2
    assert "jamais un nom" in page_2["personnes_a_charge.lien_parente"]["description"]
    assert "prestations_familiales.numero_allocataire_deposant" in page_2


def test_aucune_cle_partagee_entre_deux_pages() -> None:
    """Le merger rapproche par cle seule : une cle declaree sur deux pages
    recevrait la valeur de l'une dans les champs de l'autre."""
    vues: dict = {}
    for page_number, fields in CERFA_V2_PAGE_FIELDS.items():
        for key in fields:
            assert key not in vues, f"{key} en page {vues.get(key)} et {page_number}"
            vues[key] = page_number


def test_le_schema_couvre_les_pages_a_champs_du_cerfa() -> None:
    """Pages 1 a 11 ; la 12 n'est qu'un avertissement d'envoi."""
    assert sorted(CERFA_V2_PAGE_FIELDS) == list(range(1, 12))
