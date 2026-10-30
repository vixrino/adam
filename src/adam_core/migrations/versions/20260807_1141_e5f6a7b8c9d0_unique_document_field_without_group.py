"""unique document field without group

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-07 11:41:59.358458+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_document_field_doc_spec_no_group"


def upgrade() -> None:
    op.execute("""
        DELETE FROM document_field a
        USING document_field b
        WHERE a.group_id IS NULL
          AND b.group_id IS NULL
          AND a.document_id = b.document_id
          AND a.field_spec_id = b.field_spec_id
          AND a.id > b.id
        """)
    op.create_index(
        INDEX_NAME,
        "document_field",
        ["document_id", "field_spec_id"],
        unique=True,
        postgresql_where=sa.text("group_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="document_field")
