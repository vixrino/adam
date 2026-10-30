# Setup

Install + DB config only. Table creation (Alembic) is a separate step, not covered here.

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

## Configure the database

Copy the template and fill in your Postgres connection:

```bash
cp .env.template .env
```

```dotenv
# .env
POSTGRES_USER=nota
POSTGRES_PASSWORD=<your password>
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=nota_db
```

`adam_core/core/config.py` reads `.env` from the **current working directory** — run commands from the repo root, or export the same vars in the shell.

If the role/database don't exist yet:

```sql
CREATE ROLE nota WITH LOGIN PASSWORD '<your password>';
CREATE DATABASE nota_db OWNER nota;
```

The rest of `.env.template` (API host/port, JWT secret, PVC mount path, OCR mock) has working defaults for local dev — adjust as needed.

## Run

```bash
python scripts/run_dev.py        # dev only, reload on, http://127.0.0.1:<API_PORT>
```

At this point the app can connect to Postgres but the schema is empty — run migrations separately (`alembic upgrade head` from `src/adam_core`) before using the API.
