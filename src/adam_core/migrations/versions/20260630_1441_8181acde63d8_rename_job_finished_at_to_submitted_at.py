"""rename job finished_at to submitted_at

Revision ID: 8181acde63d8
Revises: 65a5fd7b662f
Create Date: 2026-06-30 14:41:44.959894+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8181acde63d8"
down_revision: Union[str, None] = "65a5fd7b662f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "job",
        "finished_at",
        new_column_name="submitted_at",
    )


def downgrade() -> None:
    op.alter_column(
        "job",
        "submitted_at",
        new_column_name="finished_at",
    )
