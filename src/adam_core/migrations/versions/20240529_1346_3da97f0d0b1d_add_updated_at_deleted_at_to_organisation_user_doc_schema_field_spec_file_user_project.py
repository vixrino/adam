"""add updated_at deleted_at to organisation user doc_schema field_spec file user_project"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "3da97f0d0b1d"
down_revision: Union[str, None] = "db8ff43496ec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "doc_schema",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column(
        "field_spec",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column(
        "file",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column("organisation", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "user",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column("user", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "user_project",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("user_project", "updated_at")
    op.drop_column("user", "deleted_at")
    op.drop_column("user", "updated_at")
    op.drop_column("organisation", "deleted_at")
    op.drop_column("file", "updated_at")
    op.drop_column("field_spec", "updated_at")
    op.drop_column("doc_schema", "updated_at")
