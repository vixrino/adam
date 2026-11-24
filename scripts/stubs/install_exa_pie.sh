#!/bin/sh
# Installs the exa_pie stub into the project venv (editable). `uv sync` removes it again: re-run.
cd "$(dirname "$0")/../.." || exit 1
uv pip install --python .venv/bin/python -e scripts/stubs/exa_pie
