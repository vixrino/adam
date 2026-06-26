"""update enums"""

from typing import Sequence, Union

from alembic import op

revision: str = "6452f2c7b5b5"
down_revision: Union[str, None] = "42e721054714"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
