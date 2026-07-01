"""Format formulaire v0.3 interface contract for seed and OCR ingestion."""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Tuple

from pydantic import BaseModel, Field

from adam_core.enums.status import FieldValueType


class FormValue(BaseModel):
    type: str
    text: Optional[str] = None
    value: Optional[Any] = None
    raw_text: Optional[str] = None
    polygon: List[float] = Field(default_factory=lambda: [0, 0, 0, 0, 0, 0, 0, 0])
    confidence: float = 1.0


class FormKVPair(BaseModel):
    id: str
    label: str
    group_id: Optional[str] = None
    value: FormValue

    @property
    def field_key(self) -> str:
        return self.id

    @property
    def extracted_value(self) -> str:
        v = self.value
        if v.type == "boolean":
            return str(v.value).lower()
        if v.type == "text":
            return v.text or ""
        if v.type in ("date", "datetime", "number"):
            return str(v.value if v.value is not None else v.text or "")
        return str(v.text or v.value or "")

    @property
    def confidence(self) -> float:
        return self.value.confidence

    @property
    def polygon(self) -> List[float]:
        return self.value.polygon


class FormSection(BaseModel):
    id: str
    label: str
    kv_pairs: List[FormKVPair] = Field(default_factory=list)


class FormPage(BaseModel):
    page_number: int
    width: int = 0
    height: int = 0
    sections: List[FormSection] = Field(default_factory=list)


class FormDocument(BaseModel):
    format_version: str
    document_id: str
    coordinate_unit: str = "pixel"
    page_count: int
    pages: List[FormPage] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def iter_kv_pairs(self) -> Iterator[Tuple[FormPage, FormSection, FormKVPair]]:
        for page in self.pages:
            for section in page.sections:
                for kv in section.kv_pairs:
                    yield page, section, kv

    def extract_field_specs(self) -> List[Dict[str, Any]]:
        specs: List[Dict[str, Any]] = []
        order = 0
        for page in self.pages:
            for section in page.sections:
                for kv in section.kv_pairs:
                    vtype = kv.value.type.upper()
                    if vtype == "TEXT":
                        ftype = FieldValueType.TEXT.value
                    elif vtype == "BOOLEAN":
                        ftype = FieldValueType.BOOLEAN.value
                    elif vtype == "NUMBER":
                        ftype = FieldValueType.NUMBER.value
                    elif vtype == "DATE":
                        ftype = FieldValueType.DATE.value
                    elif vtype == "DATETIME":
                        ftype = FieldValueType.DATETIME.value
                    else:
                        ftype = FieldValueType.TEXT.value
                    specs.append(
                        {
                            "page": page.page_number,
                            "section_id": section.id,
                            "section_label": section.label,
                            "field_key": kv.field_key,
                            "display_label": kv.label,
                            "value_type": ftype,
                            "required": False,
                            "display_order": order,
                            "polygon": kv.polygon,
                            "group_id": kv.group_id,
                        }
                    )
                    order += 1
        return specs
