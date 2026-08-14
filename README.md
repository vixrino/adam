# ADAM - Annotation et Données Automatisées

uv run pytest tests/unit/test_resolve_caller.py tests/unit/test_jwt_middleware.py -q
uv run pytest tests/unit -q          # rien cassé ailleurs
uv run python -c "import exa_pie; print('ok')"
