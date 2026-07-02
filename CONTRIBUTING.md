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
