from adam_core.schemas.interface_contract import FormDocument


def test_form_document_minimal() -> None:
    doc = FormDocument.model_validate(
        {
            "format_version": "0.3",
            "document_id": "test",
            "page_count": 1,
            "pages": [],
        }
    )
    assert doc.page_count == 1
    assert doc.extract_field_specs() == []


def _doc_with_single_field(value_type: str) -> FormDocument:
    return FormDocument.model_validate(
        {
            "format_version": "0.3",
            "document_id": "test",
            "page_count": 1,
            "pages": [
                {
                    "page_number": 1,
                    "sections": [
                        {
                            "id": "section_1",
                            "label": "SECTION_1",
                            "kv_pairs": [
                                {
                                    "id": "field_1",
                                    "label": "FIELD_1",
                                    "value": {"type": value_type, "value": "2024-01-15T10:30:00"},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )


def test_extract_field_specs_maps_datetime_type() -> None:
    doc = _doc_with_single_field("datetime")
    specs = doc.extract_field_specs()
    assert specs[0]["value_type"] == "DATETIME"


def test_extract_field_specs_maps_date_type() -> None:
    doc = _doc_with_single_field("date")
    specs = doc.extract_field_specs()
    assert specs[0]["value_type"] == "DATE"


def test_extract_field_specs_unknown_type_falls_back_to_text() -> None:
    doc = _doc_with_single_field("unknown_type")
    specs = doc.extract_field_specs()
    assert specs[0]["value_type"] == "TEXT"
