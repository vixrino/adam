# Contribuer au projet ADAM

## Branches

- `main` <- production, protégée, merge via MR uniquement
- `develop` <- intégration continue, base de toutes les branches
- `feature/xxx` <- nouvelle fonctionnalité (depuis develop)
- `fix/xxx` <- correction de bug (depuis develop)

## Convention de commits

Format : `<type>(<scope>): <description courte>`

| Type | Usage |
| :--- | :--- |
| `feat` | Nouvelle fonctionnalité |
| `fix` | Correction de bug |
| `refactor` | Refactoring sans changement fonctionnel |
| `test` | Ajout ou modification de tests |
| `docs` | Documentation uniquement |
| `chore` | Outillage, config, dépendances |
| `migration` | Migration Alembic |

### Exemples

- `feat(orm): add FieldSpec model with section_id and polygon constraint`
- `feat(api): add GET /documents/{id}/fields/by-section endpoint`
- `fix(session): handle special characters in POSTGRES_PASSWORD via URL.create`
- `migration: init tables labellisation`
- `chore(config): add pylint and coverage quality gates`
- `docs(adam_core): add README with Alembic workflow`

## Quality Gates

Avant merge sur `develop` :

| Métrique | Seuil |
| :--- | :--- |
| Pylint score | >= 9.0 / 10 |
| Couverture de tests | >= 80% |
| Alembic migrations | `alembic upgrade head` sans erreur |
| API startup | `uvicorn` démarre sans erreur |

### Commandes de vérification

```bash
python -m pylint src/adam_core src/adam_api
python -m pytest --cov=src --cov-report=term-missing
cd src/adam_core && python -m alembic upgrade head
```

## Workflow Sprint

1. Créer la branche : `git checkout -b feature/ma-feature develop`
2. Développer + commit au fil de l'eau
3. Vérifier les quality gates localement
4. Push : `git push origin feature/ma-feature`
5. Ouvrir une Merge Request vers `develop`
6. Review + merge

```text
Remplacement de tous les retours `Dict[str, Any]` non typés par des schemas Pydantic stricts, centralisés dans `adam_core/schemas/responses.py`.

Ce qui a été fait

  46 schemas Pydantic créés, répartis en 10 catégories :

    - Organisation
    - Project
    - Dataset
    - File
    - Document
    - Job
    - Ingestion
    - OCR
    - Schema
    - User

  Chaque endpoint expose désormais un `response_model` explicite.

Techniques utilisées

  - `ConfigDict(from_attributes=True)` pour la sérialisation ORM directe.
  - `validation_alias` pour mapper `metadata_` → `metadata`.
  - Schemas imbriqués pour les vues détaillées (`DocumentFullOut`, `JobDetailOut`).
  - Schemas spécialisés par verbe HTTP (aucun schema générique réutilisé).
  - Champs calculés injectés manuellement :
      - `documents_count`
      - `field_specs_created`
      - statistiques de dataset

Logique métier ajoutée

  - Garde de verrouillage `423 Locked` sur les mutations de `FieldSpec`.
  - Protection d'intégrité référentielle `409 Conflict` lors de la suppression d'une `FieldSpec`.
  - `page_count` exposé via une `@property` ORM sur `Document`.

Tests

  295 tests passent (1 échec non lié aux schemas).

    - 45  test_schemas_responses
        Schemas Pydantic purs

    - 39  test_router_schemas

    - 28  test_router_organisations

    - 26  test_router_users

    - 25  test_router_documents

    - 24  test_router_projects

    - 21  test_router_jobs

    - 16  test_router_files

    - 16  test_router_datasets

    - 15  test_router_ocr

    - 14  test_service_ingestion

    - 10  test_service_consensus

    - 7   test_hashing
```
