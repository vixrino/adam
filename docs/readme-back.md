# README - Backend NOTA

Le backend de NOTA reçoit les formulaires, les fait lire par l'IA, gère la vérification par les opérateurs et mesure la qualité de la lecture. Il expose une API REST utilisée par le frontend.

**Sommaire**

* Ce que fait le backend
* Organisation du code
* Installer le projet
* Lancer le projet
* Base de données et migrations
* Vérifier le code avant de pousser
* Scripts utiles
* Configuration
* Pour aller plus loin

---

## Ce que fait le backend

1. **Réception :** un PDF déposé est contrôlé (PDF valide, bon nombre de pages, pas déjà reçu), puis stocké sur le PVC.
2. **Images :** chaque page est transformée en image PNG à 300 DPI, pour l'affichage.
3. **Préremplissage :** l'IA (Mistral) reconnaît chaque page, remet le document dans l'ordre et propose une valeur pour chaque champ.
4. **Vérification :** les opérateurs valident ou corrigent les valeurs ; le consensus retient la valeur finale.
5. **Tests de qualité :** l'IA relit des documents déjà vérifiés et l'outil compare les deux réponses (métriques, rapport PDF).

---

## Organisation du code

| Dossier | Contenu |
| --- | --- |
| `src/nota_core/` | Partagé par l'API et les workers : modèles de base de données, migrations Alembic, schémas Pydantic, configuration, calcul des métriques |
| `src/nota_api/` | API FastAPI : routes (`routers/`), services, dépendances (authentification, droits) |
| `src/nota_worker/` | Traitements automatiques : images des pages, préremplissage, suivi de l'avancement, consensus, tests de qualité ; connecteurs OCR (`connectors/`) |
| `scripts/` | Seed, diagnostics, migrations de données, banc d'essai |
| `tests/` | Tests automatiques (pytest) |
| `conf/` | Configuration exa-pie : `pie.yaml` (DEV), `pie.prod.yaml` (PROD) |
| `docs/` | Documentation : sécurité, schéma de base (`schema.dbml`), roadmap |
| `launcher.py` | Point d'entrée unique : API, workers ou les deux |

---

## Installer le projet

**Prérequis :** Python 3.12, [uv](https://docs.astral.sh/uv/), PostgreSQL, accès au registre interne (paquets `exa-pie` et `exa-logger`).

```powershell
cd C:\DEV\nota-back
uv sync --all-extras
copy .env.template .env
```

Ensuite, remplir `.env` (voir **Configuration**). Pour un premier lancement en DEV, les valeurs du modèle suffisent, sauf `POSTGRES_PASSWORD`.

> Le projet s'installe uniquement avec **uv**, jamais avec pip. Les outils de développement (pytest, black, mypy…) et les paquets internes sont des extras : d'où `--all-extras`.

---

## Lancer le projet

```powershell
# API + tous les workers, dans une seule fenêtre
uv run --all-extras python launcher.py

# Ou séparément
uv run --all-extras python launcher.py api
uv run --all-extras python launcher.py worker
```

* API : http://localhost:8000
* Documentation interactive (Swagger) : http://localhost:8000/docs
* Sondes : `GET /health` (API démarrée), `GET /db-check` (base joignable)

En mode `all`, chaque ligne du journal commence par `[api]` ou `[worker]`.

**Premier lancement :** créer le schéma CERFA et un lot de documents.

```powershell
uv run --all-extras python scripts\seed.py --reset
# ou, avec un vrai formulaire qui sera lu par l'IA :
uv run --all-extras python scripts\seed.py --reset --pdf C:\chemin\cerfa.pdf
```

---

## Base de données et migrations

Le schéma de la base est géré **uniquement** par Alembic (`src/nota_core/migrations/`).

```powershell
cd src\nota_core
uv run --all-extras alembic upgrade head     # appliquer les migrations
uv run --all-extras alembic heads            # doit afficher une seule tête
uv run --all-extras alembic revision --autogenerate -m "description"   # nouvelle migration
```

* Une migration se relit toujours avant d'être poussée : l'autogénération ne voit pas tout (renommages, données).
* En cas de « multiple heads » : `powershell -ExecutionPolicy Bypass -File scripts\diag_migrations.ps1`.
* La description complète des tables est dans la page **01 - Documentation BDD**.

---

## Vérifier le code avant de pousser

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run-checks.ps1
```

| Outil | Vérifie | Seuil |
| --- | --- | --- |
| isort, black | Mise en forme (lignes de 100 caractères) | Aucun écart |
| pylint | Qualité du code | Note ≥ 9,0 / 10 |
| mypy | Typage | Aucune erreur |
| bandit | Sécurité du code | Aucune faille moyenne ou haute |
| pytest | Tests et couverture | Tous verts, couverture ≥ 80 % |

Lancer seulement les tests : `uv run --all-extras python -m pytest -q`.

Les mêmes contrôles tournent dans Jenkins, suivis du quality gate SonarQube (voir la page **Déploiement et exploitation**).

---

## Scripts utiles

Tous se lancent depuis la racine du dépôt, avec `uv run --all-extras python scripts\<script>`.

| Script | Rôle |
| --- | --- |
| `seed.py` | Crée le schéma CERFA et un lot ; `--pdf` ajoute un vrai formulaire |
| `test_connection.py` | Vérifie la connexion à PostgreSQL |
| `verifier_schema.py` | Montre ce que l'IA lira d'un schéma (pages et champs) |
| `diag_prepopulation.py` | Explique le préremplissage d'un document réel |
| `diag_ocr_mistral.py` | Teste l'accès à Mistral, étape par étape |
| `lancer_benchmark.py` | Lance un test de qualité complet en une commande (`--contre N` pour rejouer et comparer à l'exécution N) |
| `exporter_rapport_pdf.py` | Écrit le rapport PDF d'une exécution, sans interface |
| `diag_ecarts.py` | Détaille les écarts d'une exécution |
| `corriger_verite.py` | Corrige la vérification humaine d'un champ que l'interface ne rouvre plus |
| `diag_migrations.ps1` | État des migrations Alembic |

> `lancer_benchmark.py` appelle vraiment l'IA quand `OCR_MOCK_ENABLED=false` : environ 35 appels par formulaire. `--dry-run` montre ce qui serait lancé, sans rien appeler.

---

## Configuration

Tout passe par des variables d'environnement : `.env` en DEV (modèle : `.env.template`), Vault Kubernetes ailleurs. Aucun secret n'est écrit dans le code ni commité.

| Catégorie | Variables principales |
| --- | --- |
| Base de données | `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` |
| API | `API_HOST`, `API_PORT`, `API_CORS_ORIGINS` (doit contenir l'adresse du frontend, ex. `https://localhost:4200`) |
| Authentification | `API_DISABLE_JWT_VALIDATION`, `API_DEV_MATRICULE`, `PIE_CONFIG_FILE`, `INTERNAL_AUTH_ENABLED`, `INTERNAL_API_KEY` |
| Stockage | `PVC_MOUNT_PATH` |
| OCR | `OCR_MOCK_ENABLED`, `OCR_TIMEOUT_SECONDS`, `MISTRAL_API_KEY`, `MISTRAL_OCR_ENDPOINT`, `MISTRAL_OCR_MODEL`, `MISTRAL_ANNOTATION_MODEL`, `MISTRAL_CA_BUNDLE` |
| Annuaire | `AD_ENABLED`, `AD_HOST`, `AD_BIND_DN`, `AD_PASSWORD`, `AD_BASE_DN`… |
| Tests de qualité | `COMPARISON_HMAC_KEY` |
| Journaux | `LOG_LEVEL`, `LOG_FORMAT` |

**En DEV, sans authentification :** `API_DISABLE_JWT_VALIDATION=true`, et `API_DEV_MATRICULE` égal au matricule d'un utilisateur qui existe dans la table `user`. Toutes les requêtes sont alors faites en son nom.

> **ATTENTION** : `API_DISABLE_JWT_VALIDATION=true` et `OCR_MOCK_ENABLED=true` sont réservés au DEV, jamais en INTÉGRATION ni en PROD.

---

## Pour aller plus loin

| Page | Contenu |
| --- | --- |
| C01 - Stack et Environnements | Technologies et environnements |
| C02 - Déploiement et exploitation | Jenkins, SonarQube, déploiement, incidents |
| 01 - Documentation BDD | Toutes les tables et colonnes |
| B02 - Catalogue de scénarios | Comportement attendu dans chaque situation |
| `docs/securite-exa-pie.md` | Branchement de l'authentification |
| `CONTRIBUTING.md` | Branches, convention de commits, quality gates |
