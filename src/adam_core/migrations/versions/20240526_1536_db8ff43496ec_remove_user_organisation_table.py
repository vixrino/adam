"""remove user_organisation table"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "db8ff43496ec"
down_revision: Union[str, None] = "c09d1d040b3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    op.drop_column("user_project", "created_at")
