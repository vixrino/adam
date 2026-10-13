# ADAM - Annotation et Données Automatisées

[https://vibeslops.luckeysystems.com/](https://t.co/8r990RLwpe)

uv run --all-extras python scripts\creer_execution_test.py --dataset-id 8

uv run --all-extras python -c "from sqlalchemy import inspect; from nota_core.models import TestRecipe; print('config' in inspect(TestRecipe).columns)"
