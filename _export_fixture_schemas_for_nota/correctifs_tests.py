# Correctifs des tests nota — voir NOTES.md pour ou coller chaque bloc.


# --- 1. tests/unit/test_router_schemas.py : dans _make_schema, avant `return row`

    row.locked = False
    row.specimen_file = None


# --- 2. tests/unit/test_router_schemas.py : helper a ajouter apres _make_field_spec

def _get_by_model(mock_db: AsyncMock, schema: Any, spec: Any) -> None:
    """db.get rend le schema pour DocSchema, le field_spec pour le reste.

    Sans ca, db.get(DocSchema) rend le field_spec, dont l'attribut `locked`
    est un MagicMock, donc vrai : _reject_if_locked leve 409.
    """
    mock_db.get.side_effect = lambda model, _id: (
        schema if model.__name__ == "DocSchema" else spec
    )


# --- 3. TestPatchFieldSpec et TestDeleteFieldSpec : partout ou le test ecrit
#        mock_db.get.return_value = fs
#     remplacer par
#        _get_by_model(mock_db, _make_schema(id=1), fs)


# --- 4. src/nota_api/routers/documents.py : patch_document_field, le return

    return DocumentFieldPatchOut(
        id=df.id,
        status=df.status,
        resolved_value=df.resolved_value,
        ocr_polygon=df.ocr_polygon,
    )
