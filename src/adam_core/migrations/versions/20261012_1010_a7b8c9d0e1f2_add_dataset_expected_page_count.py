"""add dataset.expected_page_count

Le nombre de pages exige des PDF ingeres etait un reglage global
(INGESTION_PAGE_COUNT). Or un dataset porte un type de document, et tous
n'ont pas le meme nombre de pages : le controle est donc porte par le
dataset. NULL = aucun controle, ce qui garde le comportement actuel des
datasets existants.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dataset",
        sa.Column(
            "expected_page_count",
            sa.Integer(),
            nullable=True,
            comment=(
                "Nombre de pages exige des PDF ingeres (12 pour le CERFA) ; NULL = "
                "aucun controle. Un PDF hors taille est cree en ERROR."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("dataset", "expected_page_count")
