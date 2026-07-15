# Export pour nota — worker images de pages + endpoint de service

Fichiers prêts à copier vers nota, imports déjà renommés `adam_*` → `nota_*`.
**Règle : ne jamais écraser un fichier existant de nota avec une copie d'adam**
(les deux repos ont divergé, notamment `schemas/responses.py`). Les fichiers
ci-dessous sont classés selon qu'ils se copient tels quels ou se greffent.

## MR 1 — page image worker (branche worker existante)

Copies telles quelles (fichiers nouveaux sur nota) :

| Fichier export                      | Destination nota                        |
|-------------------------------------|-----------------------------------------|
| `nota_worker/__init__.py`           | `src/nota_worker/__init__.py`           |
| `nota_worker/base_worker.py`        | `src/nota_worker/base_worker.py`        |
| `nota_worker/page_image_worker.py`  | `src/nota_worker/page_image_worker.py`  |
| `nota_core/utils/pdf_render.py`     | `src/nota_core/utils/pdf_render.py`     |
| `tests/unit/test_page_image_worker.py` | `tests/unit/`                        |
| `tests/unit/test_pdf_render.py`     | `tests/unit/`                           |

À greffer (ne pas écraser) :

- `nota_worker/main.py` : version de référence qui n'enregistre que
  `PageImageWorker`. Si nota a déjà un `main.py` avec d'autres workers,
  ajouter seulement `PageImageWorker()` à sa liste `workers`.

Note : `pdf_render.py` contient aussi les helpers `page_image_filename` /
`page_image_relative_path` utilisés par l'endpoint (MR 2). Les garder ici
ou les déplacer dans le commit de la MR 2, au choix — mais ils doivent
exister avant de merger l'endpoint.

## MR 2 — endpoint GET /documents/{id}/pages/{n} (branche créée depuis la branche worker)

- `nota_api/routers/documents_page_image_SNIPPET.py` : imports + fonction
  `get_document_page_image` à greffer dans le `documents.py` **de nota**
  (le reste du documents.py d'adam contient du code d'autres tickets qui
  ne compile pas sur nota : `value_type`, schémas divergents).
- `tests/unit/test_router_documents_page_image.py` : autonome, à déposer
  tel quel dans `tests/unit/` de nota.

## Fixture

- `test_fixture.pdf` : PDF de test à checksum connu pour valider le worker
  manuellement.
