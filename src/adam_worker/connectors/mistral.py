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

Le rang d'une image dans le PDF ne dit pas quelle page du CERFA elle porte :
un deposant qui scanne dans le desordre, oublie une page ou en glisse une
d'un autre formulaire ferait annoter une page avec le schema d'une autre, et
les valeurs atterriraient dans les mauvais champs sans aucune erreur. Chaque
page est donc d'abord identifiee : apres l'OCR, un appel court demande au
modele d'annotation quelle page du CERFA porte ce texte, d'apres ses
rubriques imprimees (CERFA_V2_PAGE_TITLES), pages sans champs comprises. C'est
le schema de la page reconnue qui sert a l'annotation, quel
que soit son rang. Tout ecart entre rang et page reconnue — page deplacee,
page inattendue, page en double, page a champs introuvable — est journalise
et rendu dans les metadonnees du document, sous "anomalies_pages".

Consequence : toutes les pages passent a l'OCR, y compris les pages
d'information, puisqu'une page a champs peut se trouver a n'importe quel
rang. Une page reconnue comme sans champs n'est pas annotee, et une page dont
l'OCR ne rend aucun texte n'est ni identifiee ni annotee.

Erreurs : moteur injoignable, statut non-2xx epuisant les reprises, ou reponse
illisible levent OcrConnectorError. Un moteur joignable qui ne detecte aucun
champ rend None — cas nominal, le document sera pre-alimente vide.
"""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

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
from adam_core.schemas.cerfa_v2 import CERFA_V2_PAGE_FIELDS, CERFA_V2_PAGE_TITLES, FieldDef

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
    "Une case cochee rend true. Une case non cochee rend null : ne pas avoir "
    "coche n'est pas avoir repondu non.\n"
    "Exception, et elle est frequente : quand plusieurs cases repondent a une "
    "meme question et s'excluent — oui/non, ou une liste de situations dont "
    "une seule vaut — cocher l'une repond pour toutes. Les autres rendent "
    "alors false, pas null. Si aucune n'est cochee dans le groupe, toutes "
    "rendent null.\n"
    "Une case non cochee n'appelle aucune date, aucun montant et aucun "
    "libelle : les champs qui en dependent restent null. De meme, un champ "
    "que la reponse cochee prive d'objet — un numero de dossier alors que la "
    "case « aucun dossier precedent » est cochee — rend null.\n"
    "Si une rubrique porte plusieurs lignes, ne rends que la premiere. Ne "
    "concatene jamais plusieurs lignes dans un meme champ.\n"
    "Les en-tetes, pieds de page, references de formulaire, numeros de notice "
    "et mentions d'impression ne sont pas des donnees saisies : ignore-les. "
    "Une rubrique laissee vide par le deposant rend null pour tous ses champs, "
    "meme si des chiffres ou des dates figurent ailleurs sur la page.\n"
    "Une date incomplete — une annee seule, un mois et une annee — rend null : "
    "ne complete jamais un jour ou un mois qui n'est pas ecrit. Une annee a "
    "deux chiffres se lit au siecle le plus plausible (17/09/69 rend "
    "1969-09-17)."
)

#: Nom du json_schema d'identification, distinct de celui de l'annotation.
_IDENTIFICATION = "identification_page"


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
        page_fields: Optional[Mapping[int, Mapping[str, FieldDef]]] = None,
        page_titles: Optional[Mapping[int, str]] = None,
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
        # Sentinelle plutot que la constante en valeur par defaut : un dict en
        # defaut est partage par tous les appels, et les linters le signalent
        # meme quand le type annonce, Mapping, interdit deja de l'ecrire.
        self.page_fields = CERFA_V2_PAGE_FIELDS if page_fields is None else page_fields
        titles = CERFA_V2_PAGE_TITLES if page_titles is None else page_titles
        self._descriptions = _descriptions_pages(self.page_fields, titles)
        self._consigne_identification = _consigne_identification(self._descriptions)
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
        anomalies: List[Dict[str, Any]] = []
        #: page du CERFA reconnue -> rang de l'image qui la porte.
        reconnues: Dict[int, int] = {}
        detected = 0
        for rang, image in enumerate(images, start=1):
            markdown, dims = await self._read_page(image, rang)
            if not markdown.strip():
                # Page illisible ou vide : rien a identifier ni a annoter.
                continue
            page_number = await self._identify(markdown, rang)
            anomalie = _anomalie(rang, page_number, reconnues, self._descriptions)
            if anomalie is not None:
                logger.warning("page du CERFA inattendue : %s", anomalie)
                anomalies.append(anomalie)
                if anomalie["type"] == "page_en_double":
                    continue
            if page_number is None:
                continue
            reconnues[page_number] = rang
            fields = self.page_fields.get(page_number)
            if not fields:
                # Page reconnue mais sans champs : rien a annoter.
                continue
            annotation = await self._extract_fields(markdown, page_number, fields)
            page = self._build_page(page_number, fields, annotation, dims)
            detected += sum(1 for _, _, kv in _iter_pairs(page) if kv.value is not None)
            pages.append(page)

        manquantes = sorted(set(self.page_fields) - set(reconnues))
        if manquantes:
            anomalie = {"type": "pages_manquantes", "pages": manquantes}
            logger.warning("pages du CERFA introuvables : %s", manquantes)
            anomalies.append(anomalie)

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
                "anomalies_pages": anomalies,
            },
        )

    # -- Appel de l'API -----------------------------------------------------

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

    async def _identify(self, markdown: str, rang: int) -> Optional[int]:
        """Rend la page du CERFA que porte ce texte, ou None si aucune page
        decrite ne correspond. Une reponse hors des pages decrites vaut None :
        mieux vaut ne rien annoter qu'annoter avec le schema d'une autre page.
        """
        payload = {
            "model": self.annotation_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": self._consigne_identification},
                {"role": "user", "content": markdown},
            ],
            "response_format": _identification_format(),
        }
        reponse = _contenu_json(await self._post("/v1/chat/completions", payload, rang), rang)
        page = reponse.get("page")
        # bool est un int en Python : True ne doit pas se lire page 1.
        if isinstance(page, int) and not isinstance(page, bool) and page in self._descriptions:
            return page
        return None

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
        return _flatten(_contenu_json(data, page_number), set(fields))

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
                        body = response.json()
                    except ValueError as exc:
                        raise OcrConnectorError(
                            f"reponse non JSON pour la page {page_number} : {exc}"
                        ) from exc
                    # Un JSON valide n'est pas forcement un objet : une reponse
                    # reduite a une liste ou a une chaine passerait le decodage
                    # et casserait plus loin, a la premiere lecture de cle.
                    if not isinstance(body, dict):
                        raise OcrConnectorError(
                            f"reponse JSON non objet pour la page {page_number} : "
                            f"{type(body).__name__}"
                        )
                    return body
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


def _contenu_json(data: Mapping[str, Any], page_number: int) -> Dict[str, Any]:
    """Objet JSON rendu par une completion ; {} si elle ne rend rien."""
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
                f"reponse du modele illisible pour la page {page_number} : {exc}"
            ) from exc
    if not isinstance(raw, dict):
        raise OcrConnectorError(
            f"reponse du modele pour la page {page_number} : objet attendu, recu {type(raw).__name__}"
        )
    return raw


def _descriptions_pages(
    page_fields: Mapping[int, Mapping[str, FieldDef]], titles: Mapping[int, str]
) -> Dict[int, str]:
    """Description de chaque page reconnaissable : ses rubriques imprimees, ou
    a defaut celles qu'on deduit des cles de son schema."""
    descriptions = dict(titles)
    for page_number, fields in page_fields.items():
        if page_number not in descriptions:
            rubriques = dict.fromkeys(key.split(".", 1)[0] for key in fields)
            descriptions[page_number] = ", ".join(r.replace("_", " ") for r in rubriques)
    return dict(sorted(descriptions.items()))


def _consigne_identification(descriptions: Mapping[int, str]) -> str:
    """Consigne d'identification. Elle insiste sur le contenu contre le rang :
    un modele qui numerote les pages dans l'ordre ou il les recoit se trompe
    des qu'un document est scanne dans le desordre, et c'est arrive."""
    lignes = "\n".join(f"- page {n} : {d}" for n, d in descriptions.items())
    return (
        "Tu recois la transcription d'une seule page du formulaire CERFA de "
        "depot d'un dossier de surendettement. Dis quelle page du formulaire "
        "elle porte. Voici les pages, decrites par leurs rubriques imprimees :\n"
        + lignes
        + "\nIdentifie la page par ses titres de rubrique uniquement. Le "
        "document a pu etre scanne dans le desordre : rien ne permet de "
        "deduire le numero de la page de sa place dans le document. La "
        "reference de formulaire en pied de page est la meme sur toutes les "
        "pages et ne distingue rien.\n"
        "Les pages 9, 10 et 11 portent des tableaux de prets semblables. La "
        "page 9 se reconnait a son titre, credits immobiliers. Les pages 10 et "
        "11 ouvrent toutes deux sur les credits a la consommation : une page "
        "qui porte aussi les rubriques autres prets et cautionnements, ou "
        "cause de votre situation de surendettement, est la page 11 ; sans "
        "elles, c'est la page 10.\n"
        "Rends null si la page n'est aucune de celles-ci : notice, autre "
        "document, page illisible. Ne choisis pas la plus proche par defaut : "
        "une page attribuee a tort fait relever ses valeurs dans les champs "
        "d'une autre."
    )


def _identification_format() -> Dict[str, Any]:
    """json_schema strict d'une seule propriete, le numero de page ou null."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": _IDENTIFICATION,
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"page": {"type": ["integer", "null"]}},
                "required": ["page"],
                "additionalProperties": False,
            },
        },
    }


def _anomalie(
    rang: int,
    page_number: Optional[int],
    reconnues: Mapping[int, int],
    descriptions: Mapping[int, Any],
) -> Optional[Dict[str, Any]]:
    """Ecart entre le rang d'une image et la page qu'elle porte, s'il y en a.

    None a un rang qu'aucune page decrite n'occupe n'en est pas un : c'est le
    cas d'une page du formulaire dont on n'a pas releve les rubriques.
    """
    if page_number is None:
        if rang in descriptions:
            return {"type": "page_inattendue", "rang": rang, "page_attendue": rang}
        return None
    if page_number in reconnues:
        return {
            "type": "page_en_double",
            "rang": rang,
            "page_reconnue": page_number,
            "rang_retenu": reconnues[page_number],
        }
    if page_number != rang:
        return {"type": "page_deplacee", "rang": rang, "page_reconnue": page_number}
    return None


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


def _iter_pairs(page: Page) -> Iterator[Tuple[int, Section, KVPair]]:
    for section in page.sections:
        for kv in section.kv_pairs:
            yield page.page_number, section, kv
