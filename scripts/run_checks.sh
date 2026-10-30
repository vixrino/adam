#!/usr/bin/env bash
# Equivalent bash de run_checks.ps1, avec selection des etapes.
#   scripts/run_checks.sh                 toutes les etapes par defaut
#   scripts/run_checks.sh pylint pytest   seulement celles-la
#   scripts/run_checks.sh -k pylint pytest  idem, sans s'arreter au premier echec
#   scripts/run_checks.sh -f              black/isort reecrivent les fichiers (sinon --check)
#   scripts/run_checks.sh -l              liste les etapes
# Etapes : requirements black isort pylint mypy bandit pytest (mypy hors defaut, comme dans le .ps1).
# Pas de `uv sync` : il retirerait les stubs de scripts/stubs/.
set -uo pipefail
cd "$(dirname "$0")/.."

DEFAULT="requirements black isort pylint bandit pytest"
KEEP_GOING=0 FIX=0
while getopts "kfl" o; do
    case $o in
        k) KEEP_GOING=1 ;;
        f) FIX=1 ;;
        l) echo "$DEFAULT mypy"; exit 0 ;;
        *) exit 2 ;;
    esac
done
shift $((OPTIND - 1))
STEPS=${*:-$DEFAULT}

if command -v uv >/dev/null; then RUN=(uv run --no-sync); else RUN=(python -m); fi
CHECK=(--check); [ $FIX = 1 ] && CHECK=()

step() {
    case $1 in
        black)  "${RUN[@]}" black "${CHECK[@]}" src/ ;;
        isort)  "${RUN[@]}" isort "${CHECK[@]}" src/ ;;
        pylint) "${RUN[@]}" pylint src/ ;;
        mypy)   "${RUN[@]}" mypy src/ --strict --ignore-missing-imports ;;
        bandit) "${RUN[@]}" bandit -ll -r src/ ;;
        pytest) "${RUN[@]}" pytest -p no:cacheprovider --cov=. --cov-report=term-missing ;;
        *) echo "etape inconnue: $1" >&2; return 2 ;;
    esac
}

failed=()
for s in $STEPS; do
    echo "==== $s ===="
    if step "$s"; then echo "[OK] $s"; else
        echo "[X] $s a echoue"; failed+=("$s")
        [ $KEEP_GOING = 1 ] || exit 1
    fi
done
[ ${#failed[@]} = 0 ] && echo "Tout est passe." || { echo "Echecs: ${failed[*]}"; exit 1; }
