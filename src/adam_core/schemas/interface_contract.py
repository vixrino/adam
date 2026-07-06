"""Contrat d'interface Smartdoc v0.3.

Format JSON produit par l'OCR (et par les seeds/fixtures de test) et consomme
par l'API pour peupler DocSchema/FieldSpec/DocumentField. Un SmartdocDocument
represente un formulaire scanne : une liste de pages, chacune decoupee en
sections, chacune contenant des paires cle/valeur (KVPair) correspondant aux
champs du formulaire.

Le type de chaque valeur extraite (`KVValue.type`) est un format fixe impose
par le contrat OCR ("text", "number", "date", "datetime", "boolean") et ne
doit pas etre confondu avec l'enum interne FieldValueType (en majuscule) qui
represente la taxonomie de champs cote base de donnees. `extract_field_specs`
fait le pont entre les deux.
"""

from __future__ import annotations

from typing import Annotated, Any, Dict, Iterator, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field

from adam_core.enums.status import FieldValueType

_FIELD_VALUE_TYPE_BY_WIRE_TYPE = {
    "text": FieldValueType.TEXT.value,
    "number": FieldValueType.NUMBER.value,
    "date": FieldValueType.DATE.value,
    "datetime": FieldValueType.DATETIME.value,
    "boolean": FieldValueType.BOOLEAN.value,
}


class KVTextValue(BaseModel):
    """Valeur de type texte libre extraite par l'OCR.

    `text` est obligatoire : un champ sans donnee doit etre represente par
    KVPair.value = None, pas par un KVTextValue avec `text` absent.
    """

    type: Literal["text"] = "text"
    text: str
    raw_text: Optional[str] = None
    polygon: Optional[List[float]] = None
    confidence: float = 1.0


class KVNumberValue(BaseModel):
    """Valeur numerique extraite par l'OCR.

    `value` est obligatoire mais reste `Any` : l'OCR peut renvoyer un nombre
    deja parse ou une chaine brute non convertible (ex: "12 BIS"), a charge
    de field_parser de tenter la conversion en aval, sans jamais lever
    d'exception. Un champ sans donnee doit etre represente par
    KVPair.value = None, pas par un KVNumberValue avec `value` absent.
    """

    type: Literal["number"] = "number"
    value: Any
    raw_text: Optional[str] = None
    polygon: Optional[List[float]] = None
    confidence: float = 1.0


class KVDateValue(BaseModel):
    """Valeur de type date (sans heure) extraite par l'OCR.

    `value` est obligatoire : un champ sans donnee doit etre represente par
    KVPair.value = None, pas par un KVDateValue avec `value` absent.
    """

    type: Literal["date"] = "date"
    value: str
    raw_text: Optional[str] = None
    polygon: Optional[List[float]] = None
    confidence: float = 1.0


class KVDatetimeValue(BaseModel):
    """Valeur de type date+heure extraite par l'OCR.

    `value` est obligatoire : un champ sans donnee doit etre represente par
    KVPair.value = None, pas par un KVDatetimeValue avec `value` absent.
    """

    type: Literal["datetime"] = "datetime"
    value: str
    raw_text: Optional[str] = None
    polygon: Optional[List[float]] = None
    confidence: float = 1.0


class KVBooleanValue(BaseModel):
    """Valeur booleenne extraite par l'OCR (ex: case a cocher).

    `value` est obligatoire : un champ sans donnee doit etre represente par
    KVPair.value = None, pas par un KVBooleanValue avec `value` absent.
    """

    type: Literal["boolean"] = "boolean"
    value: bool
    raw_text: Optional[str] = None
    polygon: Optional[List[float]] = None
    confidence: float = 1.0


KVValue = Annotated[
    Union[KVTextValue, KVBooleanValue, KVNumberValue, KVDateValue, KVDatetimeValue],
    Field(discriminator="type"),
]
"""Union discriminee sur `type` : un `type` absent de ce contrat fait
echouer la validation Pydantic des la lecture du JSON, avant meme
d'atteindre `extract_field_specs`."""


class KVPair(BaseModel):
    """Un champ du formulaire, identifie par `id` (ex: "deposant.nom"),
    avec sa valeur OCR optionnelle (absente si le champ n'a pas ete
    detecte sur le document)."""

    id: str
    key: Optional[str] = None
    label: Optional[str] = None
    group_id: Optional[str] = None
    value: Optional[KVValue] = None

    @property
    def field_key(self) -> str:
        return self.id

    @property
    def display_label(self) -> str:
        """Libelle a afficher a l'operateur : label, sinon key, sinon id."""
        return self.label or self.key or self.id

    @property
    def section_id(self) -> str:
        """Premier segment de `id` (ex: "deposant" pour "deposant.nom")."""
        return self.id.split(".", 1)[0]

    @property
    def value_type(self) -> Optional[str]:
        """Type au format contrat OCR (minuscule), ou None si pas de valeur."""
        return self.value.type if self.value else None

    @property
    def extracted_value(self) -> Optional[str]:
        """Valeur serialisee en string, telle que stockee en base
        (DocumentField.ocr_value), avant reconversion par field_parser."""
        v = self.value
        if v is None:
            return None
        if v.type == "boolean":
            return str(v.value).lower()
        if v.type == "text":
            return v.text or ""
        if v.type in ("date", "datetime", "number"):
            return str(v.value if v.value is not None else v.raw_text or "")
        return str(v.raw_text or v.value or "")

    @property
    def confidence(self) -> float:
        return self.value.confidence if self.value else 0.0

    @property
    def polygon(self) -> Optional[List[float]]:
        return self.value.polygon if self.value else None


class Section(BaseModel):
    """Regroupement logique de champs au sein d'une page (ex: "Deposant")."""

    id: str
    label: str
    kv_pairs: List[KVPair] = Field(default_factory=list)


class Page(BaseModel):
    """Une page du document scanne, avec ses metadonnees d'image."""

    page_number: int
    width: int = 0
    height: int = 0
    dpi: Optional[int] = 150
    angle_deg: Optional[float] = 0.0
    sections: List[Section] = Field(default_factory=list)


class SmartdocDocument(BaseModel):
    """Racine du contrat Smartdoc v0.3 : un formulaire scanne complet."""

    smartdoc_version: Literal["0.3"]
    document_id: str
    coordinate_unit: Literal["inch", "mm", "pixel"] = "pixel"
    page_count: int
    pages: List[Page] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict, min_length=1)

    def iter_kv_pairs(self) -> Iterator[Tuple[int, Section, KVPair]]:
        """Aplati pages/sections/kv_pairs en un flux (page_number, section, kv)."""
        for page in self.pages:
            for section in page.sections:
                for kv in section.kv_pairs:
                    yield page.page_number, section, kv

    def extract_field_specs(self) -> List[Dict[str, Any]]:
        """Derive les FieldSpec (schema du formulaire) depuis les KVPair.

        Deduplique par (section_id, field_key) : un champ repetable
        (plusieurs `group_id` pour un meme `id`, ex: plusieurs dettes)
        ne genere qu'une seule FieldSpec, les instances individuelles
        etant portees par DocumentField.group_id en aval.
        """
        specs: List[Dict[str, Any]] = []
        seen: set[Tuple[str, str]] = set()
        order = 0
        for page in self.pages:
            for section in page.sections:
                for kv in section.kv_pairs:
                    dedup_key = (section.id, kv.field_key)
                    if dedup_key in seen:
                        continue
                    seen.add(dedup_key)
                    if kv.value_type is None:
                        ftype = FieldValueType.TEXT.value
                    else:
                        try:
                            ftype = _FIELD_VALUE_TYPE_BY_WIRE_TYPE[kv.value_type]
                        except KeyError:
                            raise ValueError(
                                f"Type de valeur OCR non supporte {kv.value_type!r} "
                                f"pour le champ {kv.field_key!r}"
                            ) from None
                    specs.append(
                        {
                            "page": page.page_number,
                            "section_id": section.id,
                            "section_label": section.label,
                            "field_key": kv.field_key,
                            "display_label": kv.display_label,
                            "value_type": ftype,
                            "required": False,
                            "display_order": order,
                            "polygon": kv.polygon,
                            "group_id": kv.group_id,
                        }
                    )
                    order += 1
        return specs
