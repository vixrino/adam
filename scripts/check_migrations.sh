#!/usr/bin/env bash
# Controle de derive : applique les migrations sur un Postgres jetable, puis verifie
# que les modeles n'ont rien de plus (alembic check). A lancer avant une PR qui
# touche aux modeles. Necessite Docker.
#   scripts/check_migrations.sh
#   PG_IMAGE=postgres:16 CHECK_PORT=55432 scripts/check_migrations.sh
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE=${PG_IMAGE:-postgres:16}
PORT=${CHECK_PORT:-55432}
NAME=nota-migration-check
PY=${PYTHON:-$([ -x .venv/bin/python ] && echo .venv/bin/python || echo python)}

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker run -d --rm --name "$NAME" -e POSTGRES_PASSWORD=check -e POSTGRES_DB=nota_check \
    -p "$PORT:5432" "$IMAGE" >/dev/null
trap 'docker rm -f "$NAME" >/dev/null 2>&1 || true' EXIT

for _ in $(seq 1 30); do
    docker exec "$NAME" pg_isready -U postgres -d nota_check >/dev/null 2>&1 && break
    sleep 1
done
docker exec "$NAME" pg_isready -U postgres -d nota_check >/dev/null

# Le .env du poste ne doit pas viser une autre base : on impose la base jetable.
export POSTGRES_HOST=localhost POSTGRES_PORT="$PORT" POSTGRES_USER=postgres \
    POSTGRES_PASSWORD=check POSTGRES_DB=nota_check
export MIGRATION_POSTGRES_USER="" MIGRATION_POSTGRES_PASSWORD=""
export PYTHONPATH=src

echo "== upgrade head"
"$PY" launcher.py migrate
echo "== alembic check"
"$PY" -c "
from alembic import command
from adam_core.db.migrate import alembic_config
command.check(alembic_config())
"
echo "OK : migrations et modeles concordent"
