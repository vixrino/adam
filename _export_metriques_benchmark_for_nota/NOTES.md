# Report vers nota : metriques du benchmark et endpoints

`changements.patch` = ce que `feature/metriques-benchmark` ajoute par dessus
`feature/worker-tests-batch` (15 fichiers), `adam_*` renomme en `nota_*`.
A appliquer APRES le patch du worker. Les migrations d'adam n'y sont pas :
le script de migration cree celle de nota.

Verifie : applique sur une copie du worker aux paquets renommes, 824 tests
passent.

    git apply --check changements.patch
    git apply changements.patch
    uv run --all-extras python scripts\migrer_expected_page_count.py --dry-run
    uv run --all-extras python scripts\migrer_expected_page_count.py
    uv run --all-extras pytest

Puis redemarrer l'API et les workers, et relancer la recette (l'execution 1,
anterieure aux metriques, n'a pas de matrice) :
POST /api/v1/test-executions {"recipe_id": <id>}.

## Si `git apply --check` refuse certains fichiers

Ils different dans nota (adaptes a la main). Appliquer le reste, puis :

    git apply --reject changements.patch

- `scripts/migrer_expected_page_count.py`, `tests/unit/test_benchmark.py` :
  remplacer par les copies de `fichiers_complets/` (deja en nota_*), puis
  supprimer leurs `.rej`.
- `src/nota_api/main.py` : ajouter l'import
  `from nota_api.routers.benchmark import router as benchmark_router`
  et `app.include_router(benchmark_router, prefix=PREFIX, dependencies=[Depends(get_caller)])`.
- `src/nota_core/models/test_recipe.py` : ajouter la colonne `config` (JSONB),
  voir le `.rej`.
- Supprimer tous les `.rej` une fois reportes : `git status` les liste.
