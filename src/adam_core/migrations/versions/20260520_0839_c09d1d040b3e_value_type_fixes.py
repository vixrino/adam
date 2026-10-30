"""Value Type fixes

Revision ID: c09d1d040b3e
Revises: dbce215342c7
Create Date: 2026-05-20 08:39:03.205752+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c09d1d040b3e"
down_revision: Union[str, None] = "dbce215342c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # No backfill needed — fresh DB, field_proposal is empty
    op.alter_column("field_proposal", "value_type", existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    op.alter_column("field_proposal", "value_type", existing_type=sa.String(), nullable=True)
    # ### end Alembic commands ###
