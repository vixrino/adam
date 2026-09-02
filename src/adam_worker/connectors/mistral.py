"""Connecteur OCR Mistral : une passe par page avec json_schema d'annotation.

La configuration reprise ici est celle que le script de qualification
test_mistral_configuration.py a validee sur des CERFA fictifs : cible OCR (et
non un modele multimodal prompte), envoi page par page, et json_schema de
sortie fourni des l'appel. C'est ce schema qui resout le coeur du ticket T5 :
comme ses proprietes sont les cles pointees du contrat ("deposant.nom", ...),
l'annotation rendue par Mistral porte directement les field_key que le merger
sait rapprocher, sans rapprochement de polygones apres coup.

Consequence assumee : l'annotation ne rend pas de position. Les KVPair sortent
sans polygone et le merger retombe sur celui du FieldSpec, ce que la chaine de
pre-alimentation prevoit deja pour les champs non detectes.

Les pages sans schema (pages d'information du CERFA) ne sont pas soumises :
rien a y extraire, autant d'appels economises.

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


class MistralOcrConnector(BaseOcrConnector):
    """Soumet chaque image de page a l'API OCR Mistral et assemble la reponse."""

    name = "mistral"

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        *,
        model: str = "mistral-ocr-latest",
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
            metadata={"provider": "mistral", "model": self.model},
        )

    # -- Appel de l'API -----------------------------------------------------

    async def _annotate(
        self, image: Path, page_number: int, fields: Mapping[str, FieldDef]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Une passe OCR sur une image, rend (annotation aplatie, dimensions)."""
        payload = {
            "model": self.model,
            "document": {"type": "image_url", "image_url": self._data_uri(image)},
            "document_annotation_format": _annotation_format(page_number, fields),
            "include_image_base64": False,
        }
        data = await self._post(payload, page_number)

        raw = data.get("document_annotation")
        if raw is None:
            return {}, _dimensions(data)
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
        return _flatten(raw, set(fields)), _dimensions(data)

    async def _post(self, payload: Dict[str, Any], page_number: int) -> Dict[str, Any]:
        """POST /v1/ocr avec reprises sur erreurs reseau et 5xx, comme ApiClient."""
        url = f"{self.endpoint}/v1/ocr"
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
                    raise OcrConnectorError(
                        f"appel OCR refuse pour la page {page_number} "
                        f"(statut {response.status_code})"
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


def _annotation_format(page_number: int, fields: Mapping[str, FieldDef]) -> Dict[str, Any]:
    """json_schema strict, plat, tel que qualifie par le script du manager."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": f"Page {page_number}",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {key: dict(spec) for key, spec in fields.items()},
                "required": [],
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
