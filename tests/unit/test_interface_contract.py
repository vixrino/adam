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
