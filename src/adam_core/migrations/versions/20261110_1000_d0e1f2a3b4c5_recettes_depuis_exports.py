"""recettes de benchmark depuis un export de dataset, versionnees

Un benchmark ne mesure rien de stable sur un dataset en cours de modification :
les recettes partent desormais d'un export, lot fige de documents avec
l'empreinte du schema du moment. Elles sont versionnees : la modifier une fois
figee, c'est en creer la version suivante, sous le meme nom.

- dataset_export : nouvelle table ;
- test_recipe : dataset_export_id, tout_l_export, version, recette_racine_id ;
  l'unicite (dataset_id, name) devient (dataset_id, name, version).

Le schema Postgres est nomme explicitement, celui des modeles
(Base.metadata.schema : « nota » dans nota, aucun dans adam) : la migration ne
depend pas d'un search_path que env.py poserait ou non.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from adam_core.db.base import Base

revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = Base.metadata.schema


def _ref(table: str) -> str:
    """Cible d'une cle etrangere, qualifiee par le schema s'il y en a un."""
    return f"{SCHEMA}.{table}.id" if SCHEMA else f"{table}.id"


def upgrade() -> None:
    op.create_table(
        "dataset_export",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("schema_id", sa.Integer(), nullable=False),
        sa.Column("schema_hash", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("document_ids", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            [_ref("dataset")],
            name="fk_dataset_export_dataset_id_dataset",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["schema_id"],
            [_ref("doc_schema")],
            name="fk_dataset_export_schema_id_doc_schema",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            [_ref("user")],
            name="fk_dataset_export_created_by_user_id_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_dataset_export"),
        sa.UniqueConstraint("dataset_id", "name", name="uq_dataset_export_dataset_name"),
        schema=SCHEMA,
    )
    op.create_index("ix_dataset_export_dataset_id", "dataset_export", ["dataset_id"], schema=SCHEMA)

    for colonne in (
        sa.Column("dataset_export_id", sa.Integer(), nullable=True),
        sa.Column("tout_l_export", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("recette_racine_id", sa.Integer(), nullable=True),
    ):
        op.add_column("test_recipe", colonne, schema=SCHEMA)
    op.create_foreign_key(
        "fk_test_recipe_dataset_export_id_dataset_export",
        "test_recipe",
        "dataset_export",
        ["dataset_export_id"],
        ["id"],
        ondelete="RESTRICT",
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_test_recipe_recette_racine_id_test_recipe",
        "test_recipe",
        "test_recipe",
        ["recette_racine_id"],
        ["id"],
        ondelete="RESTRICT",
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
    )
    op.create_index(
        "ix_test_recipe_dataset_export_id", "test_recipe", ["dataset_export_id"], schema=SCHEMA
    )
    op.create_index(
        "ix_test_recipe_recette_racine_id", "test_recipe", ["recette_racine_id"], schema=SCHEMA
    )
    op.drop_constraint("uq_test_recipe_dataset_name", "test_recipe", type_="unique", schema=SCHEMA)
    op.create_unique_constraint(
        "uq_test_recipe_dataset_name_version",
        "test_recipe",
        ["dataset_id", "name", "version"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    # Echoue s'il existe plusieurs versions d'une recette : on ne supprime pas
    # de donnees pour revenir en arriere.
    op.drop_constraint(
        "uq_test_recipe_dataset_name_version", "test_recipe", type_="unique", schema=SCHEMA
    )
    op.create_unique_constraint(
        "uq_test_recipe_dataset_name", "test_recipe", ["dataset_id", "name"], schema=SCHEMA
    )
    op.drop_index("ix_test_recipe_recette_racine_id", table_name="test_recipe", schema=SCHEMA)
    op.drop_index("ix_test_recipe_dataset_export_id", table_name="test_recipe", schema=SCHEMA)
    for contrainte in (
        "fk_test_recipe_recette_racine_id_test_recipe",
        "fk_test_recipe_dataset_export_id_dataset_export",
    ):
        op.drop_constraint(contrainte, "test_recipe", type_="foreignkey", schema=SCHEMA)
    for colonne in ("recette_racine_id", "version", "tout_l_export", "dataset_export_id"):
        op.drop_column("test_recipe", colonne, schema=SCHEMA)
    op.drop_index("ix_dataset_export_dataset_id", table_name="dataset_export", schema=SCHEMA)
    op.drop_table("dataset_export", schema=SCHEMA)
