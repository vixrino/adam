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
