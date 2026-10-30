"""merge heads

Revision ID: 69fe667dd59f
Revises: e5f6a7b8c9d0, 289059f04c71
Create Date: 2026-10-12 12:46:09.605288+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "69fe667dd59f"
down_revision: Union[str, None] = ("e5f6a7b8c9d0", "289059f04c71")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
