"""metriques du benchmark OCR

Matrice de l'extraction (vp, fp, fn, vn, substitutions) et libelles figes sur
evaluation_report, version du comparateur et empreinte du schema sur
test_execution, config du test sur test_recipe.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from adam_core.db.base import Base

revision: str = "ab2743943078"
down_revision: Union[str, None] = "release_1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from sqlalchemy.dialects import postgresql

_COMPTES = ("vp", "fp", "fn", "vn", "substitutions", "somme_distance", "somme_longueur_attendue")

SCHEMA = Base.metadata.schema


def upgrade() -> None:
    for nom in _COMPTES:
        op.add_column(
            "evaluation_report",
            sa.Column(nom, sa.Integer(), nullable=False, server_default="0"),
            schema=SCHEMA,
        )
    op.add_column(
        "evaluation_report", sa.Column("page", sa.Integer(), nullable=True), schema=SCHEMA
    )
    op.add_column(
        "evaluation_report", sa.Column("section_id", sa.String(), nullable=True), schema=SCHEMA
    )
    op.add_column(
        "evaluation_report", sa.Column("value_type", sa.String(), nullable=True), schema=SCHEMA
    )
    op.add_column(
        "evaluation_report",
        sa.Column("sensitive", sa.Boolean(), nullable=False, server_default="false"),
        schema=SCHEMA,
    )
    op.add_column(
        "test_execution",
        sa.Column("comparateur_version", sa.String(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "test_execution", sa.Column("schema_hash", sa.String(), nullable=True), schema=SCHEMA
    )
    op.add_column(
        "test_recipe",
        sa.Column(
            "config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("test_recipe", "config", schema=SCHEMA)
    op.drop_column("test_execution", "schema_hash", schema=SCHEMA)
    op.drop_column("test_execution", "comparateur_version", schema=SCHEMA)
    for nom in ("sensitive", "value_type", "section_id", "page", *reversed(_COMPTES)):
        op.drop_column("evaluation_report", nom, schema=SCHEMA)
