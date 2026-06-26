"""update DocumentStatus"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "65a5fd7b662f"
down_revision: Union[str, None] = "6452f2c7b5b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "field_spec",
        "polygon",
        existing_type=postgresql.ARRAY(sa.DOUBLE_PRECISION(precision=53)),
        comment="4 points (x1,y1,x2,y2,x3,y3,x4,y4). 8 floats si non null",
        existing_comment="4 points (x1,y1,x2,y2,x3,y3,x4,y4) - 8 floats si non null",
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "field_spec",
        "polygon",
        existing_type=postgresql.ARRAY(sa.DOUBLE_PRECISION(precision=53)),
        comment="4 points (x1,y1,x2,y2,x3,y3,x4,y4) - 8 floats si non null",
        existing_comment="4 points (x1,y1,x2,y2,x3,y3,x4,y4). 8 floats si non null",
        existing_nullable=True,
    )
