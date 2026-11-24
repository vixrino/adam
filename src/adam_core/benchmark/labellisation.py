"""La labellisation d'un document, au contrat Smartdoc v0.3.

C'est la verite humaine (document_field.resolved_value) rangee comme le ferait
un moteur : memes pages, sections et ``id`` de champ. Elle accompagne le PDF dans
l'archive d'un export, et se rejoue comme un JSON SMARTDOC (score attendu 100 %).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from adam_core.enums.status import FieldValueType
from adam_core.schemas.interface_contract import (
    KVBooleanValue,
    KVDatetimeValue,
    KVDateValue,
    KVNumberValue,
    KVPair,
    KVTextValue,
    KVValue,
    Page,
    Section,
    SmartdocDocument,
)
from adam_core.utils.field_parser import parse_field_value

_VRAI = {"true", "1", "yes", "oui"}


@dataclass(frozen=True)
class ChampLabellise:
    page: int
    section_id: str
    section_label: str
    field_key: str
    display_label: str
    value_type: str
    group_id: Optional[str]
    valeur: Optional[str]
    polygon: Optional[List[float]] = None


def _valeur(champ: ChampLabellise) -> Optional[KVValue]:
    brut = champ.valeur
    if brut is None or brut == "":
        return None
    polygon = champ.polygon
    type_ = champ.value_type
    if type_ == FieldValueType.BOOLEAN.value:
        return KVBooleanValue(value=brut.strip().lower() in _VRAI, polygon=polygon)
    if type_ == FieldValueType.NUMBER.value:
        return KVNumberValue(value=parse_field_value(brut, type_), raw_text=brut, polygon=polygon)
    if type_ == FieldValueType.DATE.value:
        return KVDateValue(
            value=str(parse_field_value(brut, type_)), raw_text=brut, polygon=polygon
        )
    if type_ == FieldValueType.DATETIME.value:
        return KVDatetimeValue(value=brut, raw_text=brut, polygon=polygon)
    return KVTextValue(text=brut, polygon=polygon)


def labelled_document(
    *,
    document_id: int,
    file_name: str,
    page_count: Optional[int],
    champs: List[ChampLabellise],
    export_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Le JSON de labellisation : ``champs`` dans l'ordre du schema."""
    pages: Dict[int, Dict[str, Section]] = {}
    for champ in champs:
        sections = pages.setdefault(champ.page, {})
        section = sections.setdefault(
            champ.section_id, Section(id=champ.section_id, label=champ.section_label)
        )
        section.kv_pairs.append(
            KVPair(
                id=champ.field_key,
                label=champ.display_label,
                group_id=champ.group_id,
                value=_valeur(champ),
            )
        )
    nb_pages = max([page_count or 0, *pages]) if pages or page_count else 1
    document = SmartdocDocument(
        smartdoc_version="0.3",
        document_id=str(document_id),
        page_count=nb_pages,
        pages=[
            Page(page_number=numero, sections=list(pages[numero].values()))
            for numero in sorted(pages)
        ],
        metadata={
            "source": "nota-labellisation",
            "file_name": file_name,
            **({"export_id": export_id} if export_id is not None else {}),
        },
    )
    return document.model_dump(mode="json", exclude_none=True)
