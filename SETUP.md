# Setup

Install, database and configuration. The schema is created by the launcher (see **Migrations**).

## Prerequisites

- Python 3.12
- A reachable PostgreSQL instance (local or remote)

## Install

```bash
uv sync                          # dev deps included
```

Without `uv` (CI / plain `pip`):

```bash
pip install --group dev -e .     # editable, needed for `pytest --cov` to hit src/
# or, deployment image:
pip install .
```

## Configure

Copy the template and fill in your Postgres connection:

```bash
cp .env.template .env
```

`adam_core/core/config.py` reads `.env` from the **current working directory** — run commands from the repo root, or export the same vars in the shell. The template is grouped by prefix (application, database, API, authentication, OCR, Active Directory, benchmark) and has working defaults for local dev.

If the role/database don't exist yet:

```sql
CREATE ROLE nota WITH LOGIN PASSWORD '<your password>';
CREATE DATABASE nota_db OWNER nota;
```

## Run

```bash
python launcher.py all           # migrates, then starts the API and the workers
python launcher.py migrate       # migration only
```

## Migrations

`launcher.py all` applies Alembic (`upgrade head`) **once**, in the parent process, before starting the children; `api` and `worker` never migrate. NOTA runs as a **single pod**, so no lock is taken: with several replicas, concurrent migrations would need to be serialized (for example a `pg_advisory_xact_lock` in `env.py`). If the database holds a revision this code does not know, the launcher stops with exit code 1.

The baseline is `release_1`, with the Alembic version table inside schema `nota`. After a model change: `alembic revision --autogenerate`, review, commit. `scripts/check_migrations.sh` checks for drift between the models and the migrations (needs Docker).

Two database accounts in production:

| Account | Env vars | Used by |
|---|---|---|
| admin (DDL) | `MIGRATION_POSTGRES_USER` / `MIGRATION_POSTGRES_PASSWORD` | the migration only; may create schema `nota` |
| `web` (DML only) | `POSTGRES_USER` / `POSTGRES_PASSWORD` | the API and the workers |

Leave `MIGRATION_*` empty in dev: the migration then uses `POSTGRES_*`. Grants of `web` are managed directly in the database.

## Settings stored in the database

These are not environment variables: they live in table `app_setting` (key → JSON value) and are read on each worker cycle or request, with no cache. Change one with SQL, no restart:

```sql
INSERT INTO nota.app_setting (key, value, updated_by)
VALUES ('worker.PrepopulationWorker.poll_interval', '60', 'me')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by;
```

| Key | Default when absent | Meaning |
|---|---|---|
| `ocr_enabled` | `true` | `false` makes `ocr` documents wait; `empty` ones still go through |
| `ad_enabled` | `false` | Active Directory lookup; on if the env var `AD_ENABLED` **or** this key is true (the env var forces it, the key can only turn it on) |
| `worker.<Class>.poll_interval` | the worker's class default | seconds between cycles, minimum 1 |
| `ocr_status` | — | written by the prepopulation worker: `{"reachable": bool}` |

`<Class>` is `PageImageWorker`, `ConsensusWorker`, `PrepopulationWorker` or `TestExecutionWorker`. `scripts/seed.py` inserts the four delays for local testing; in production the class defaults apply until a row is inserted.

## Secrets

In production these come from the Vault, never from a committed file:

| Variable | Notes |
|---|---|
| `POSTGRES_PASSWORD` | `web` account |
| `MIGRATION_POSTGRES_PASSWORD` | admin account, migration only |
| `INTERNAL_API_KEY` | shared by the services; 32 characters minimum outside dev |
| `MISTRAL_API_KEY` | OCR engine |
| `AD_PASSWORD` | Active Directory service account |
| `COMPARISON_HMAC_KEY` | rotating it invalidates the historical fingerprints of the benchmark |
