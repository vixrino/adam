"""
Tests unitaires adam_core/schemas/interface_contract.py
"""

from adam_core.schemas.interface_contract import (
    KVPair,
    KVBooleanValue,
    KVDateValue,
    KVDatetimeValue,
    KVNumberValue,
    KVTextValue,
    Page,
    Section,
    SmartdocDocument,
)

# ==========================================
# # Fixtures / Helpers
# ==========================================

def _text_kv(id: str = "deposant.nom", text: str = "MOULIN") -> KVPair:
    return KVPair(
        id=id,
        key="Nom",
        value=KVTextValue(type="text", text=text, confidence=0.99),
    )

def _bool_kv(id: str = "situation.marie", value: bool = True) -> KVPair:
    return KVPair(
        id=id,
        value=KVBooleanValue(type="boolean", value=value, confidence=1.0),
    )

def _section(id: str = "deposant", kv_pairs: list | None = None) -> Section:
    return Section(
        id=id,
        label=id.capitalize(),
        kv_pairs=kv_pairs or [_text_kv()],
    )

def _page(page_number: int = 1, sections: list | None = None) -> Page:
    return Page(
        page_number=page_number,
        sections=sections or [_section()]
    )

def _document(pages: list | None = None) -> SmartdocDocument:
    return SmartdocDocument(
        smartdoc_version="0.3",
        document_id="doc-001",
        coordinate_unit="pixel",
        page_count=1,
        pages=pages or [_page()],
    )


# ==========================================
# # KVPair.display_label
# ==========================================

class TestKVPairDisplayLabel:
    def test_prefers_label(self) -> None:
        kv = KVPair(id="s.f", label="Mon Label", key="Ma Cle")
        assert kv.display_label == "Mon Label"

    def test_falls_back_to_key(self) -> None:
        kv = KVPair(id="s.f", key="Ma Cle")
        assert kv.display_label == "Ma Cle"

    def test_falls_back_to_id(self) -> None:
        kv = KVPair(id="s.f")
        assert kv.display_label == "s.f"


# ==========================================
# # KVPair.section_id
# ==========================================

class TestKVPairSectionId:
    def test_returns_first_segment(self) -> None:
        kv = KVPair(id="deposant.nom")
        assert kv.section_id == "deposant"

    def test_single_segment(self) -> None:
        kv = KVPair(id="nom")
        assert kv.section_id == "nom"


# ==========================================
# # KVPair.value_type
# ==========================================

class TestKVPairValueType:
    def test_returns_type_when_value_present(self) -> None:
        kv = _text_kv()
        assert kv.value_type == "text"

    def test_returns_none_when_no_value(self) -> None:
        kv = KVPair(id="s.f")
        assert kv.value_type is None


# ==========================================
# # KVPair.extracted_value
# ==========================================

class TestKVPairExtractedValue:
    def test_text_returns_text(self) -> None:
        kv = _text_kv(text="MOULIN")
        assert kv.extracted_value == "MOULIN"

    def test_number_returns_str(self) -> None:
        kv = KVPair(
            id="s.f",
            value=KVNumberValue(type="number", raw_text="42", value=42.0, confidence=0.9),
        )
        assert kv.extracted_value == "42.0"

    def test_date_returns_value(self) -> None:
        kv = KVPair(
            id="s.f",
            value=KVDateValue(type="date", raw_text="01/01/1980", value="1980-01-01", confidence=0.95),
        )
        assert kv.extracted_value == "1980-01-01"

    def test_datetime_returns_value(self) -> None:
        kv = KVPair(
            id="s.f",
            value=KVDatetimeValue(type="datetime", raw_text="01/01/1980 10:00", value="1980-01-01T10:00", confidence=0.95),
        )
        assert kv.extracted_value == "1980-01-01T10:00"

    def test_boolean_true_returns_true(self) -> None:
        kv = _bool_kv(value=True)
        assert kv.extracted_value == "true"

    def test_boolean_false_returns_false(self) -> None:
        kv = _bool_kv(value=False)
        assert kv.extracted_value == "false"

    def test_none_value_returns_none(self) -> None:
        kv = KVPair(id="s.f")
        assert kv.extracted_value is None


# ==========================================
# # SmartdocDocument.iter_kv_pairs
# ==========================================

class TestIterKvPairs:
    def test_yields_all_kv_pairs(self) -> None:
        doc = _document()
        pairs = list(doc.iter_kv_pairs())
        assert len(pairs) == 1

    def test_yields_page_number(self) -> None:
        doc = _document()
        page_num, _, _ = list(doc.iter_kv_pairs())[0]
        assert page_num == 1

    def test_yields_section(self) -> None:
        doc = _document()
        _, section, _ = list(doc.iter_kv_pairs())[0]
        assert section.id == "deposant"

    def test_yields_kv(self) -> None:
        doc = _document()
        _, _, kv = list(doc.iter_kv_pairs())[0]
        assert kv.id == "deposant.nom"

    def test_multiple_pages_and_sections(self) -> None:
        doc = _document(pages=[
            _page(1, [_section("deposant", [_text_kv("deposant.nom")])]),
            _page(2, [_section("situation", [_bool_kv("situation.marie")])]),
        ])
        pairs = list(doc.iter_kv_pairs())
        assert len(pairs) == 2


# ==========================================
# # SmartdocDocument.extract_field_specs
# ==========================================

class TestExtractFieldSpecs:
    def test_returns_one_spec_per_unique_field(self) -> None:
        doc = _document()
        specs = doc.extract_field_specs()
        assert len(specs) == 1

    def test_spec_has_expected_keys(self) -> None:
        doc = _document()
        spec = doc.extract_field_specs()[0]
        assert "field_key" in spec
        assert "section_id" in spec
        assert "value_type" in spec
        assert "display_order" in spec

    def test_deduplicates_repeatable_fields(self) -> None:
        repeated = [
            KVPair(
                id="endettement.montant",
                group_id="dette_1",
                value=KVNumberValue(type="number", raw_text="100", value=100.0, confidence=0.9)
            ),
            KVPair(
                id="endettement.montant",
                group_id="dette_2",
                value=KVNumberValue(type="number", raw_text="200", value=200.0, confidence=0.9)
            )
        ]
        doc = _document(pages=[_page(sections=[_section("endettement", repeated)])])
        specs = doc.extract_field_specs()
        assert len(specs) == 1

    def test_display_order_is_sequential(self) -> None:
        section = _section("deposant", [
            _text_kv("deposant.nom"),
            _text_kv("deposant.prenom"),
        ])
        doc = _document(pages=[_page(sections=[section])])
        specs = doc.extract_field_specs()
        assert specs[0]["display_order"] == 0
        assert specs[1]["display_order"] == 1

    def test_value_type_defaults_to_text_when_no_value(self) -> None:
        kv = KVPair(id="deposant.nom")
        doc = _document(pages=[_page(sections=[_section("deposant", [kv])])])
        spec = doc.extract_field_specs()[0]
        assert spec["value_type"] == "TEXT"
