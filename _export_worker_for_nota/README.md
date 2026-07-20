# Export pour adam — worker images de pages + endpoint de service

Fichiers prêts à copier vers adam, imports déjà renommés `adam_*` → `adam_*`.
**Règle : ne jamais écraser un fichier existant de adam avec une copie d'adam**
(les deux repos ont divergé, notamment `schemas/responses.py`). Les fichiers
ci-dessous sont classés selon qu'ils se copient tels quels ou se greffent.

## MR 1 — page image worker (branche worker existante)

Copies telles quelles (fichiers nouveaux sur adam) :

| Fichier export                      | Destination adam                        |
|-------------------------------------|-----------------------------------------|
| `adam_worker/__init__.py`           | `src/adam_worker/__init__.py`           |
| `adam_worker/base_worker.py`        | `src/adam_worker/base_worker.py`        |
| `adam_worker/page_image_worker.py`  | `src/adam_worker/page_image_worker.py`  |
| `adam_core/utils/pdf_render.py`     | `src/adam_core/utils/pdf_render.py`     |
| `tests/unit/test_page_image_worker.py` | `tests/unit/`                        |
| `tests/unit/test_pdf_render.py`     | `tests/unit/`                           |

À greffer (ne pas écraser) :

- `adam_worker/main.py` : version de référence qui n'enregistre que
  `PageImageWorker`. Si adam a déjà un `main.py` avec d'autres workers,
  ajouter seulement `PageImageWorker()` à sa liste `workers`.

Note : `pdf_render.py` contient aussi les helpers `page_image_filename` /
`page_image_relative_path` utilisés par l'endpoint (MR 2). Les garder ici
ou les déplacer dans le commit de la MR 2, au choix — mais ils doivent
exister avant de merger l'endpoint.

## MR 2 — endpoint GET /documents/{id}/pages/{n} (branche créée depuis la branche worker)

- `adam_api/routers/documents_page_image_SNIPPET.py` : imports + fonction
  `get_document_page_image` à greffer dans le `documents.py` **de adam**
  (le reste du documents.py d'adam contient du code d'autres tickets qui
  ne compile pas sur adam : `value_type`, schémas divergents).
- `tests/unit/test_router_documents_page_image.py` : autonome, à déposer
  tel quel dans `tests/unit/` de adam.

## Fixture

- `test_fixture.pdf` : PDF de test à checksum connu pour valider le worker
  manuellement.
