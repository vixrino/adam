"""add specimen_file_id to doc_schema

Revision ID: 7260f5fd0c0f
Revises: 3e695d259679
Create Date: 2026-09-05 15:31:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "7260f5fd0c0f"
down_revision: Union[str, None] = "3e695d259679"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "doc_schema",
        sa.Column(
            "specimen_file_id",
            sa.Integer(),
            sa.ForeignKey("file.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("doc_schema", "specimen_file_id")
