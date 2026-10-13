"""metriques du benchmark OCR

Le worker de benchmark ne stockait par champ que compared et diff_count : de
quoi un taux d'ecart, pas une precision ni un rappel. Les comptes de la matrice
d'extraction (vp, fp, fn, vn, substitutions) ne se reconstituent pas apres coup,
les champs justes n'ayant pas de ligne : ils sont ecrits par le worker, les
ratios se calculent a la lecture.

- evaluation_report : matrice, sommes pour le taux d'erreur par caractere, et
  libelles figes (page, section, type, sensibilite) pour agreger sans dependre
  d'un schema qui evolue ;
- test_execution : version du comparateur et empreinte du schema, sans
  lesquelles deux scores ne se comparent pas ;
- test_recipe : config du test (seuils, champs exclus), figee avec la recette.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COMPTES = ("vp", "fp", "fn", "vn", "substitutions", "somme_distance", "somme_longueur_attendue")


def upgrade() -> None:
    for nom in _COMPTES:
        op.add_column(
            "evaluation_report",
            sa.Column(nom, sa.Integer(), nullable=False, server_default="0"),
        )
    op.add_column("evaluation_report", sa.Column("page", sa.Integer(), nullable=True))
    op.add_column("evaluation_report", sa.Column("section_id", sa.String(), nullable=True))
    op.add_column("evaluation_report", sa.Column("value_type", sa.String(), nullable=True))
    op.add_column(
        "evaluation_report",
        sa.Column("sensitive", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("test_execution", sa.Column("comparateur_version", sa.String(), nullable=True))
    op.add_column("test_execution", sa.Column("schema_hash", sa.String(), nullable=True))
    op.add_column(
        "test_recipe",
        sa.Column(
            "config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )


def downgrade() -> None:
    op.drop_column("test_recipe", "config")
    op.drop_column("test_execution", "schema_hash")
    op.drop_column("test_execution", "comparateur_version")
    for nom in ("sensitive", "value_type", "section_id", "page", *reversed(_COMPTES)):
        op.drop_column("evaluation_report", nom)
