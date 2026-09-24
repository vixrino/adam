# Tests nota en retard sur le code — correctifs

Remplace les notes precedentes : `_unlocked_db` visait le mauvais verrou.

## Cause

Nota a deux verrous. Les tests ne connaissent que l'ancien (dataset actif, 423).
Le nouveau, `_reject_if_locked`, lit `schema.locked` (409). Sur un MagicMock,
`locked` non defini est vrai → 9 tests en 409. `GET /schemas/1` plante en 500
pour la meme raison : `locked` et `specimen_file` ne se serialisent pas.

Patch et delete font `db.get(DocSchema)` puis `db.get(FieldSpec)`. Les tests
posent un seul `return_value = fs`, donc le « schema » est le field_spec.

## A porter (correctifs_tests.py)

1. `_make_schema` : `locked = False`, `specimen_file = None`.
2. Helper `_get_by_model`.
3. Patch/delete : `_get_by_model(mock_db, _make_schema(id=1), fs)`.
4. `ocr_polygon` : ici c'est la route qui est en retard, pas le test. Elle ne
   renvoie pas `ocr_polygon`. Verifier aussi que `DocumentFieldPatch` l'accepte,
   sinon il n'est pas persiste.

`_unlocked_db` devient inutile : le retirer, avec ses appels.

## Non verifie

Execute nulle part : le routeur de nota n'existe pas ici. Si `GET /schemas/1`
plante encore, lire l'erreur dans `_schema_detail_out` : un autre attribut
nouveau manque dans `_make_schema`.
