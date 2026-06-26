"""Value Type Fixes"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c09d1d040b3e"
down_revision: Union[str, None] = "dbce215342c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("field_proposal", "value_type", existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    op.alter_column("field_proposal", "value_type", existing_type=sa.String(), nullable=True)
