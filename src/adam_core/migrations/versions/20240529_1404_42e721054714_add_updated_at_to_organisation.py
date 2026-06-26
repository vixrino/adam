"""add updated_at to organisation"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "42e721054714"
down_revision: Union[str, None] = "3da97f0d0b1d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organisation",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("organisation", "updated_at")
