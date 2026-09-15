"""Connecteur OCR Mistral : OCR par page, puis annotation par un modele choisi.

L'endpoint sait faire les deux en un appel, via document_annotation_format, et
c'est ce que faisait ce connecteur. Mais l'annotation n'est pas rendue par le
modele OCR : l'endpoint la delegue a un modele de completion qu'il choisit
seul, et son defaut est mistral-small-2503. Le deploiement de la Banque ne sert
que du medium, si bien que la requete tombait en 404 « does not exist for
router completion » alors que la route repond 200 sans annotation. Aucun
parametre n'existe pour imposer ce modele : les candidats plausibles sont tous
refuses en extra_forbidden, et l'endpoint n'expose pas son schema.

Le connecteur fait donc lui-meme les deux pas : /v1/ocr rend le markdown de la
page, puis /v1/chat/completions extrait les champs de ce markdown avec le
json_schema en response_format. Deux appels par page au lieu d'un, contre le
choix explicite du modele d'annotation — qui etait de toute facon la seule
maniere de faire tourner ce connecteur ici.

Le reste du dispositif est inchange, et c'est ce qui rend la bascule tenable :
le json_schema plat dont les proprietes sont les cles pointees du contrat
("deposant.nom", ...) part maintenant en response_format au lieu de
document_annotation_format, mais l'annotation rendue porte les memes field_key,
que le merger sait deja rapprocher. C'est le coeur du ticket T5.

Consequence assumee : l'annotation ne rend pas de position. Les KVPair sortent
sans polygone et le merger retombe sur celui du FieldSpec, ce que la chaine de
pre-alimentation prevoit deja pour les champs non detectes. Les dimensions de
page, elles, restent celles que rend l'OCR.

Les pages sans schema (pages d'information du CERFA) ne sont pas soumises :
rien a y extraire, autant d'appels economises. Une page dont l'OCR ne rend
aucun texte economise de meme son second appel.

Erreurs : moteur injoignable, statut non-2xx epuisant les reprises, ou reponse
illisible levent OcrConnectorError. Un moteur joignable qui ne detecte aucun
champ rend None — cas nominal, le document sera pre-alimente vide.
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import httpx

from adam_core.schemas.interface_contract import (
    KVBooleanValue,
    KVDateValue,
    KVNumberValue,
    KVPair,
    KVTextValue,
    KVValue,
    Page,
    Section,
    SmartdocDocument,
)
from adam_core.utils.logging import get_logger
from adam_worker.connectors.base import BaseOcrConnector, OcrConnectorError
from adam_core.schemas.cerfa_v2 import CERFA_V2_PAGE_FIELDS, FieldDef

logger = get_logger(__name__)

_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = 1.0
_RETRYABLE_STATUS = range(500, 600)

_MIME_BY_SUFFIX = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

#: Consigne d'annotation. Elle n'enumere pas les champs : le json_schema passe
#: en response_format le fait deja, et le repeter en prose ouvrirait la porte a
#: une divergence entre les deux. Elle ne dit que ce que le schema ne peut pas
#: dire, et chaque phrase repond a une erreur vue sur un CERFA reel.
_CONSIGNE = (
    "Tu releves les champs d'un formulaire administratif francais a partir de "
    "sa transcription. Rends uniquement les valeurs lues dans le texte.\n"
    "Laisse null tout champ absent, illisible ou non renseigne : une valeur "
    "plausible mais non lue est une erreur, un null ne l'est jamais.\n"
    "Ne reporte jamais la valeur d'un champ dans un autre. Si une seule date "
    "figure dans une rubrique, elle renseigne le seul champ auquel elle se "
    "rapporte ; les autres restent null.\n"
    "Pour une case a cocher, rends true si elle est cochee et false si elle "
    "est vue non cochee. Une case non cochee n'appelle aucune date, aucun "
    "montant et aucun libelle : les champs qui en dependent restent null.\n"
    "Si une rubrique porte plusieurs lignes, ne rends que la premiere. Ne "
    "concatene jamais plusieurs lignes dans un meme champ.\n"
    "Les en-tetes, pieds de page, references de formulaire, numeros de notice "
    "et mentions d'impression ne sont pas des donnees saisies : ignore-les. "
    "Une rubrique laissee vide par le deposant rend null pour tous ses champs, "
    "meme si des chiffres ou des dates figurent ailleurs sur la page."
)


class MistralOcrConnector(BaseOcrConnector):
    """Soumet chaque image de page a l'API OCR Mistral et assemble la reponse."""

    name = "mistral"

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        *,
        model: str = "mistral-ocr-latest",
        annotation_model: str = "mistral-medium-latest",
        page_fields: Mapping[int, Mapping[str, FieldDef]] = CERFA_V2_PAGE_FIELDS,
        timeout_seconds: float = 30.0,
        ca_bundle: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        if not api_key:
            raise ValueError("cle d'API Mistral absente : renseigner MISTRAL_API_KEY")
        if not endpoint:
            raise ValueError("endpoint Mistral absent : renseigner MISTRAL_OCR_ENDPOINT")
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.annotation_model = annotation_model
        self.page_fields = page_fields
        # Un client injecte appartient a l'appelant, qui gere sa fermeture.
        self._external_client = client is not None
        self._client = client or httpx.AsyncClient(
            timeout=timeout_seconds,
            verify=ca_bundle or True,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    async def aclose(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    # -- Interface BaseOcrConnector -----------------------------------------

    async def extract(self, images: Sequence[Path]) -> Optional[SmartdocDocument]:
        pages: List[Page] = []
        detected = 0
        for page_number, image in enumerate(images, start=1):
            fields = self.page_fields.get(page_number)
            if not fields:
                continue
            annotation, dims = await self._annotate(image, page_number, fields)
            page = self._build_page(page_number, fields, annotation, dims)
            detected += sum(1 for _, _, kv in _iter_pairs(page) if kv.value is not None)
            pages.append(page)

        if detected == 0:
            # Aucun champ vu sur aucune page : absence de resultat, pas d'erreur.
            return None

        return SmartdocDocument(
            smartdoc_version="0.3",
            document_id="mistral",
            page_count=max(len(images), 1),
            pages=pages,
            metadata={
                "provider": "mistral",
                "model": self.model,
                "annotation_model": self.annotation_model,
            },
        )

    # -- Appel de l'API -----------------------------------------------------

    async def _annotate(
        self, image: Path, page_number: int, fields: Mapping[str, FieldDef]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Deux passes sur une image, rend (annotation aplatie, dimensions)."""
        markdown, dims = await self._read_page(image, page_number)
        if not markdown.strip():
            # Page illisible ou vide : rien a donner au modele d'annotation,
            # autant lui epargner l'appel. Absence de texte, pas une erreur.
            return {}, dims
        return await self._extract_fields(markdown, page_number, fields), dims

    async def _read_page(self, image: Path, page_number: int) -> Tuple[str, Dict[str, Any]]:
        """Passe OCR nue : rend le markdown de la page et ses dimensions."""
        payload = {
            "model": self.model,
            "document": {"type": "image_url", "image_url": self._data_uri(image)},
            "include_image_base64": False,
        }
        data = await self._post("/v1/ocr", payload, page_number)
        pages = data.get("pages") or []
        markdown = "\n\n".join(
            str(page.get("markdown") or "") for page in pages if isinstance(page, Mapping)
        )
        return markdown, _dimensions(data)

    async def _extract_fields(
        self, markdown: str, page_number: int, fields: Mapping[str, FieldDef]
    ) -> Dict[str, Any]:
        """Passe d'annotation : le json_schema part en response_format.

        temperature=0 parce qu'il s'agit de relever ce qui est ecrit : tout
        ecart d'une execution a l'autre serait du bruit, jamais une meilleure
        lecture.
        """
        payload = {
            "model": self.annotation_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": _CONSIGNE},
                {"role": "user", "content": markdown},
            ],
            "response_format": _annotation_format(page_number, fields),
        }
        data = await self._post("/v1/chat/completions", payload, page_number)

        choices = data.get("choices") or []
        if not choices:
            return {}
        raw = (choices[0].get("message") or {}).get("content")
        if raw is None or raw == "":
            return {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError as exc:
                raise OcrConnectorError(
                    f"annotation illisible pour la page {page_number} : {exc}"
                ) from exc
        if not isinstance(raw, dict):
            raise OcrConnectorError(
                f"annotation de la page {page_number} : objet attendu, recu {type(raw).__name__}"
            )
        return _flatten(raw, set(fields))

    async def _post(self, path: str, payload: Dict[str, Any], page_number: int) -> Dict[str, Any]:
        """POST avec reprises sur erreurs reseau et 5xx, comme ApiClient."""
        url = f"{self.endpoint}{path}"
        last_error = ""
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = await self._client.post(url, json=payload)
            except httpx.HTTPError as exc:
                last_error = f"erreur reseau : {exc}"
            else:
                if response.status_code in _RETRYABLE_STATUS:
                    last_error = f"statut {response.status_code}"
                elif response.is_success:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise OcrConnectorError(
                            f"reponse non JSON pour la page {page_number} : {exc}"
                        ) from exc
                else:
                    # 4xx : rejouer ne changera rien, la requete est en cause.
                    # Le corps porte le motif, que le statut seul laisse deviner.
                    raise OcrConnectorError(
                        f"appel {path} refuse pour la page {page_number} "
                        f"(statut {response.status_code}) : {response.text[:300]}"
                    )
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_BACKOFF_SECONDS * attempt)
        raise OcrConnectorError(
            f"moteur OCR injoignable pour la page {page_number} "
            f"apres {_MAX_ATTEMPTS} tentatives ({last_error})"
        )

    @staticmethod
    def _data_uri(image: Path) -> str:
        mime = _MIME_BY_SUFFIX.get(image.suffix.lower())
        if mime is None:
            raise OcrConnectorError(f"format d'image non supporte : {image.name}")
        try:
            encoded = base64.b64encode(image.read_bytes()).decode("ascii")
        except OSError as exc:
            raise OcrConnectorError(f"image illisible : {image} ({exc})") from exc
        return f"data:{mime};base64,{encoded}"

    # -- Assemblage du SmartdocDocument -------------------------------------

    def _build_page(
        self,
        page_number: int,
        fields: Mapping[str, FieldDef],
        annotation: Mapping[str, Any],
        dims: Mapping[str, Any],
    ) -> Page:
        """Itere sur le schema, jamais sur l'annotation : une cle inventee par
        le modele est ignoree, une cle attendue mais absente donne un KVPair
        sans valeur — le meme contrat que le mock et le seed."""
        sections: Dict[str, List[KVPair]] = {}
        for key, spec in fields.items():
            value = _to_kv_value(annotation.get(key), spec)
            section_id = key.split(".", 1)[0]
            sections.setdefault(section_id, []).append(KVPair(id=key, value=value))

        return Page(
            page_number=page_number,
            width=float(dims.get("width", 0) or 0),
            height=float(dims.get("height", 0) or 0),
            dpi=dims.get("dpi"),
            sections=[
                Section(id=section_id, label=section_id.capitalize(), kv_pairs=pairs)
                for section_id, pairs in sections.items()
            ],
        )


def _nullable(spec: FieldDef) -> Dict[str, Any]:
    """Autorise null a cote du type declare par le contrat.

    En sortie structuree stricte, une propriete de type "string" doit rendre
    une chaine : null n'est pas une valeur legale. Le modele somme de remplir
    une date qui n'est pas au document n'a alors pas d'autre issue que d'en
    fabriquer une — sur un CERFA reel, il a tire 1947-01-01 du pied de page du
    formulaire. Aucune consigne ne peut contredire le schema sur ce point :
    tant que null est interdit, une valeur inventee est la seule sortie
    conforme. On l'autorise donc explicitement, champ par champ.
    """
    declared = spec.get("type")
    if isinstance(declared, list):
        types = list(declared)
    else:
        types = [declared]
    if "null" not in types:
        types.append("null")
    return {**spec, "type": types}


def _annotation_format(page_number: int, fields: Mapping[str, FieldDef]) -> Dict[str, Any]:
    """json_schema strict et plat, tel que qualifie par le script du manager.

    La forme rendue vaut pour response_format comme pour l'ancien
    document_annotation_format : c'est la meme enveloppe json_schema.

    Le mode strict exige que toute propriete figure dans required : l'absence
    ne s'y exprime pas en retirant le champ, mais en autorisant null sur son
    type. Les deux vont ensemble, et required vide donnait a l'inverse un
    schema que le modele lisait comme « rends tout ce que tu peux ».
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": f"Page {page_number}",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {key: _nullable(spec) for key, spec in fields.items()},
                "required": list(fields),
                "additionalProperties": False,
            },
        },
    }


def _flatten(annotation: Mapping[str, Any], expected: set[str]) -> Dict[str, Any]:
    """Ramene l'annotation a un plat cle pointee -> valeur.

    Le schema envoye est plat, mais un modele peut regrouper par section
    ("deposant": {"deposant.nom": ...}) : on descend dans tout dictionnaire
    dont la cle n'est pas elle-meme un champ attendu.
    """
    flat: Dict[str, Any] = {}
    for key, value in annotation.items():
        if key in expected:
            flat[key] = value
        elif isinstance(value, Mapping):
            flat.update(_flatten(value, expected))
    return flat


def _to_kv_value(value: Any, spec: FieldDef) -> Optional[KVValue]:
    """Convertit une valeur d'annotation vers le type wire declare par le schema.

    None et chaine vide signifient « non detecte » et rendent None ; False, lui,
    est une detection (case vue non cochee) et est conserve.
    """
    if value is None or value == "":
        return None
    declared = spec.get("type")
    if declared == "boolean":
        return KVBooleanValue(value=bool(value))
    if declared == "number":
        return KVNumberValue(value=value)
    if spec.get("format") == "date":
        return KVDateValue(value=str(value))
    return KVTextValue(text=str(value))


def _dimensions(data: Mapping[str, Any]) -> Dict[str, Any]:
    pages = data.get("pages") or []
    if pages and isinstance(pages[0], Mapping):
        dims = pages[0].get("dimensions")
        if isinstance(dims, Mapping):
            return dict(dims)
    return {}


def _iter_pairs(page: Page):
    for section in page.sections:
        for kv in section.kv_pairs:
            yield page.page_number, section, kv
