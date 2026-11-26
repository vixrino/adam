"""reparation : colonnes de test_recipe ajoutees par d0e1f2a3b4c5, si absentes

Une base nota a ete trouvee marquee f2a3b4c5d6e7 (donc d0e1f2a3b4c5 suppose
passe) avec la table dataset_export, mais sans les quatre colonnes que cette
meme migration ajoute a test_recipe. Alembic ne rejoue pas une migration
marquee comme passee : celle-ci pose ce qui manque, et ne touche a rien de ce
qui existe deja. Sur une base saine, elle ne fait rien.

- test_recipe : dataset_export_id, tout_l_export, version, recette_racine_id,
  leurs cles etrangeres et leurs index ;
- unicite (dataset_id, name) remplacee par (dataset_id, name, version).

Le paquet *_core est deduit du chemin du fichier : la migration se copie telle
quelle d'adam a nota.
"""

import importlib
from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# .../src/<paquet>_core/migrations/versions/ce_fichier.py
Base = importlib.import_module(f"{Path(__file__).resolve().parents[2].name}.db.base").Base

revision: str = "a7c3e9d1f5b2"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = Base.metadata.schema


def _schema() -> str:
    """Schema des modeles, ou le schema courant de la connexion (adam)."""
    if SCHEMA:
        return SCHEMA
    return str(op.get_bind().execute(sa.text("SELECT current_schema()")).scalar())


def _existe(requete: str, **valeurs: str) -> bool:
    return op.get_bind().execute(sa.text(requete), valeurs).first() is not None


def _contrainte(schema: str, nom: str) -> bool:
    return _existe(
        "SELECT 1 FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace "
        "WHERE n.nspname = :schema AND c.conname = :nom",
        schema=schema,
        nom=nom,
    )


def upgrade() -> None:
    schema = _schema()
    colonnes = {
        ligne[0]
        for ligne in op.get_bind().execute(
            sa.text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = 'test_recipe'"
            ),
            {"schema": schema},
        )
    }
    for colonne in (
        sa.Column("dataset_export_id", sa.Integer(), nullable=True),
        sa.Column("tout_l_export", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("recette_racine_id", sa.Integer(), nullable=True),
    ):
        if colonne.name not in colonnes:
            op.add_column("test_recipe", colonne, schema=SCHEMA)

    for nom, colonne, cible in (
        ("fk_test_recipe_dataset_export_id_dataset_export", "dataset_export_id", "dataset_export"),
        ("fk_test_recipe_recette_racine_id_test_recipe", "recette_racine_id", "test_recipe"),
    ):
        if not _contrainte(schema, nom):
            op.create_foreign_key(
                nom,
                "test_recipe",
                cible,
                [colonne],
                ["id"],
                ondelete="RESTRICT",
                source_schema=SCHEMA,
                referent_schema=SCHEMA,
            )

    for nom, colonne in (
        ("ix_test_recipe_dataset_export_id", "dataset_export_id"),
        ("ix_test_recipe_recette_racine_id", "recette_racine_id"),
    ):
        if not _existe(
            "SELECT 1 FROM pg_indexes WHERE schemaname = :schema AND indexname = :nom",
            schema=schema,
            nom=nom,
        ):
            op.create_index(nom, "test_recipe", [colonne], schema=SCHEMA)

    if not _contrainte(schema, "uq_test_recipe_dataset_name_version"):
        if _contrainte(schema, "uq_test_recipe_dataset_name"):
            op.drop_constraint(
                "uq_test_recipe_dataset_name", "test_recipe", type_="unique", schema=SCHEMA
            )
        op.create_unique_constraint(
            "uq_test_recipe_dataset_name_version",
            "test_recipe",
            ["dataset_id", "name", "version"],
            schema=SCHEMA,
        )


def downgrade() -> None:
    # Rien a defaire : cette migration ne fait que completer d0e1f2a3b4c5, dont
    # le downgrade retire ces memes objets.
    pass
