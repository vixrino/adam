# NOTA - AnNotation et Tests Automatisés (backend)

API et traitements automatiques de NOTA : réception des formulaires, lecture par l'IA, vérification par les opérateurs et consensus, mesure de la qualité de la lecture.

> La branche `main` ne contient pas encore de release stable. Le développement actif se trouve sur la branche **`develop`**.

## Accéder au code

```bash
git clone https://scm.sofact.banque-france.fr/smartdoc/nota/nota-back.git
cd nota-back
git checkout develop
```

## Branches

| Branche | Rôle |
| :--- | :--- |
| `main` | Releases stables uniquement |
| `develop` | Développement actif, base de toutes les branches |
| `feature/*` | Nouvelles fonctionnalités, créées depuis `develop` |
| `fix/*` | Corrections de bugs, créées depuis `develop` |

Toute modification passe par une Merge Request vers `develop`. Convention de commits : `<type>(<scope>): <description>` (voir `CONTRIBUTING.md`).

## Prérequis

* Python 3.12
* [uv](https://docs.astral.sh/uv/)
* PostgreSQL
* Accès au registre interne (paquets `exa-pie` et `exa-logger`)

## Installation

**Développement (uv)**

> Le développement local utilise uv. Voir `env-setup.md` pour la procédure complète : `uv sync`, configuration `.env`, migrations, seed.

```bash
uv sync --all-extras
cp .env.template .env      # puis renseigner au moins POSTGRES_PASSWORD
```

**CI/CD et environnements sans uv (pip uniquement)**

Le projet reste installable avec `pip` seul, sans `uv` ni environnement virtuel, via les métadonnées standard de `pyproject.toml`.

```bash
# Avec les dépendances de dev (tests, lint), en mode éditable
pip install --group dev -e .

# Sans les dépendances de dev (image de déploiement / CI)
pip install .
```

Le mode éditable (`-e .`) est nécessaire en local pour que la couverture de tests (`pytest --cov`) pointe vers `src/` plutôt que vers une copie installée dans `site-packages`.

## Base de données

```bash
cd src/nota_core
uv run --all-extras alembic upgrade head     # appliquer les migrations
uv run --all-extras alembic heads            # doit afficher une seule tête
cd ../..
uv run --all-extras python scripts/seed.py --reset    # schéma CERFA et un lot de documents
```

Le schéma de la base est géré uniquement par Alembic. En cas de « multiple heads » : `scripts/diag_migrations.ps1`.

## Lancer le projet

```bash
uv run --all-extras python launcher.py            # API + tous les workers
uv run --all-extras python launcher.py api        # API seule
uv run --all-extras python launcher.py worker     # workers seuls
```

* API : `http://localhost:8000`
* Swagger : `http://localhost:8000/docs`
* Sondes : `GET /health` (API démarrée), `GET /db-check` (base joignable)

En mode `all`, chaque ligne du journal commence par `[api]` ou `[worker]`.

**En local sans SSO :** dans `.env`, `API_DISABLE_JWT_VALIDATION=true` et `API_DEV_MATRICULE=<un matricule présent dans la table user>`. Pour le frontend, ajouter `https://localhost:4200` à `API_CORS_ORIGINS`.

> **ATTENTION** : `API_DISABLE_JWT_VALIDATION=true` et `OCR_MOCK_ENABLED=true` sont réservés au développement, jamais en intégration ni en production.

## Tests et qualité

```bash
uv run --all-extras python -m pytest -q
```

Avant de pousser, `scripts/run-checks.ps1` enchaîne tous les contrôles :

| Outil | Seuil |
| :--- | :--- |
| isort, black | Mise en forme respectée (lignes de 100 caractères) |
| pylint | Note ≥ 9,0 / 10 |
| mypy | Aucune erreur de typage |
| bandit | Aucune faille moyenne ou haute |
| pytest | Tous les tests verts, couverture ≥ 80 % |

## Organisation du code

| Dossier | Rôle |
| :--- | :--- |
| `src/nota_core/` | Commun à l'API et aux workers : modèles, migrations Alembic, schémas Pydantic, configuration, métriques |
| `src/nota_api/` | API FastAPI : routes, services, authentification et droits |
| `src/nota_worker/` | Workers : images des pages, préremplissage par l'IA, avancement, consensus, tests de qualité ; connecteurs OCR |
| `scripts/` | Seed, diagnostics, migrations de données, banc d'essai |
| `tests/` | Tests pytest |
| `conf/` | Configuration exa-pie : `pie.yaml` (dev), `pie.prod.yaml` (production) |
| `launcher.py` | Point d'entrée unique : API, workers ou les deux |

## Scripts utiles

| Script | Rôle |
| :--- | :--- |
| `scripts/seed.py` | Schéma CERFA et lot de documents ; `--pdf` ajoute un vrai formulaire |
| `scripts/test_connection.py` | Vérifie la connexion à PostgreSQL |
| `scripts/lancer_benchmark.py` | Test de qualité de l'OCR en une commande ; `--contre N` rejoue l'exécution N et compare |
| `scripts/exporter_rapport_pdf.py` | Rapport PDF d'une exécution de test |
| `scripts/diag_ecarts.py` | Détail des écarts d'une exécution |
| `scripts/diag_ocr_mistral.py` | Teste l'accès à Mistral, étape par étape |

> `lancer_benchmark.py` appelle vraiment l'IA quand `OCR_MOCK_ENABLED=false` : environ 35 appels par formulaire. `--dry-run` montre ce qui serait lancé, sans rien appeler.

## Contact

* Architecte/Développeur - daniel.ferreiralara@banque-france.fr
* Développeur - lucas.teyssier@banque-france.fr
