# ADAM - Annotation et Données Automatisées

Get-Content src\nota_core\migrations\versions\20260820_1342_3e695d259679_test_recipes_data_model.py | Select-String "^revision|^down_revision"

uv run alembic -c src\nota_core\alembic.ini heads

uv run alembic -c src\nota_core\alembic.ini current
