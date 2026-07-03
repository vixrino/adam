"""Contrat d'interface Smartdoc v0.3 pour l'ingestion seed et OCR."""

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
    type: Literal["text"] = "text"
    text: Optional[str] = None
    raw_text: Optional[str] = None
    polygon: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    confidence: float = 1.0


class KVNumberValue(BaseModel):
    """`value` reste `Any` : l'OCR peut renvoyer un nombre deja parse ou une
    chaine brute non convertible (ex: "12 BIS"), a charge de field_parser."""

    type: Literal["number"] = "number"
    value: Optional[Any] = None
    raw_text: Optional[str] = None
    polygon: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    confidence: float = 1.0


class KVDateValue(BaseModel):
    type: Literal["date"] = "date"
    value: Optional[str] = None
    raw_text: Optional[str] = None
    polygon: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    confidence: float = 1.0


class KVDatetimeValue(BaseModel):
    type: Literal["datetime"] = "datetime"
    value: Optional[str] = None
    raw_text: Optional[str] = None
    polygon: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    confidence: float = 1.0


class KVBooleanValue(BaseModel):
    type: Literal["boolean"] = "boolean"
    value: Optional[bool] = None
    raw_text: Optional[str] = None
    polygon: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    confidence: float = 1.0


KVValue = Annotated[
    Union[KVTextValue, KVBooleanValue, KVNumberValue, KVDateValue, KVDatetimeValue],
    Field(discriminator="type"),
]


class KVPair(BaseModel):
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
        return self.label or self.key or self.id

    @property
    def section_id(self) -> str:
        return self.id.split(".", 1)[0]

    @property
    def value_type(self) -> Optional[str]:
        return self.value.type if self.value else None

    @property
    def extracted_value(self) -> Optional[str]:
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
    def polygon(self) -> List[float]:
        if self.value:
            return self.value.polygon
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


class Section(BaseModel):
    id: str
    label: str
    kv_pairs: List[KVPair] = Field(default_factory=list)


class Page(BaseModel):
    page_number: int
    width: int = 0
    height: int = 0
    sections: List[Section] = Field(default_factory=list)


class SmartdocDocument(BaseModel):
    smartdoc_version: Literal["0.3"]
    document_id: str
    coordinate_unit: Literal["inch", "mm", "pixel"] = "pixel"
    page_count: int
    pages: List[Page] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def iter_kv_pairs(self) -> Iterator[Tuple[int, Section, KVPair]]:
        for page in self.pages:
            for section in page.sections:
                for kv in section.kv_pairs:
                    yield page.page_number, section, kv

    def extract_field_specs(self) -> List[Dict[str, Any]]:
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
                    ftype = _FIELD_VALUE_TYPE_BY_WIRE_TYPE.get(kv.value_type or "", FieldValueType.TEXT.value)
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
