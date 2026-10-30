"""add description, sensitive to field_spec

Revision ID: 289059f04c71
Revises: d1c9e8c82314
Create Date: 2026-09-12 18:03:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "289059f04c71"
# NB: dans le repo officiel, ajuster a la HEAD locale (id + nom de fichier).
down_revision: Union[str, None] = "d1c9e8c82314"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "field_spec",
        sa.Column(
            "sensitive",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column("field_spec", sa.Column("description", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("field_spec", "description")
    op.drop_column("field_spec", "sensitive")
