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

Commit 1 — Support des formats français
feat(field-parser): support French date, number and space-separated formats

DATE/DATETIME fall back to JJ/MM/AAAA (slash/dash/dot/space separators)
when ISO 8601 parsing fails. NUMBER falls back to French notation
(space/nbsp thousand separators, comma decimal separator).
→ fichier concerné : nota_core/utils/field_parser.py

Commit 2 — Correctifs et durcissement
fix(field-parser): map DATETIME field type and harden edge cases

- interface_contract.extract_field_specs was missing a DATETIME branch
- strip surrounding whitespace before DATE/DATETIME parsing
- reject non-finite NUMBER results (nan/inf/-inf)
→ fichiers concernés : interface_contract.py, field_parser.py

Commit 3 — Tests et script de validation
test(field-parser): add unit tests, fixture and standalone JSON script

- unit tests covering all value_type/format combinations
- test_fixture_all_types.json covering every format variant
- scripts/test_with_json.py to validate a real JSON file without
  a running server/database
→ fichiers concernés : tests/unit/test_field_parser.py, scripts/test_fixture_all_types.json, scripts/test_with_json.py


Résumé Merge Request
Ajout et durcissement du parser de valeurs de champs (parse_field_value), qui convertit les valeurs brutes OCR en types Python/JSON natifs (TEXT, NUMBER, DATE, DATETIME, BOOLEAN) de façon tolérante — jamais d'exception, retour de la valeur brute si non convertible.

Fonctionnalités
- Parsing typé intégré à GET /documents/{id}/fields
- Support des formats français : dates JJ/MM/AAAA (/, -, ., espace), nombres avec séparateur de milliers et virgule décimale
- Repli automatique sur ISO 8601 en priorité, formats FR en fallback

Corrections
- Type DATETIME manquant dans extract_field_specs (champs datetime jamais parsés côté API)
- Nettoyage des espaces superflus avant parsing DATE/DATETIME (sortie OCR)
- Rejet des valeurs NUMBER non finies (nan/inf/-inf)

Tests
- 43 tests unitaires couvrant tous les types et cas limites (formats invalides, valeurs non convertibles, séparateurs mixtes)
- Script scripts/test_with_json.py + fixture test_fixture_all_types.json pour validation manuelle sans serveur/DB
