"""add locked to doc_schema

Revision ID: d1c9e8c82314
Revises: 7260f5fd0c0f
Create Date: 2026-09-06 19:29:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d1c9e8c82314"
# NB: dans le repo officiel, ajuster a la HEAD locale (id + nom de fichier).
down_revision: Union[str, None] = "7260f5fd0c0f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "doc_schema",
        sa.Column(
            "locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("doc_schema", "locked")
