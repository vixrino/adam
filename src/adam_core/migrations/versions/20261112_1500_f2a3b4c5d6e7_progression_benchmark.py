"""progression et annulation des executions de benchmark

- test_execution.documents_traites : documents passes, compares ou ecartes,
  pour la progression (documents_compared ne compte que les compares) ;
- statut CANCELLED : la colonne status est une chaine sans contrainte, seul son
  commentaire change.

Schema nomme explicitement, comme d0e1f2a3b4c5.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from adam_core.db.base import Base

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = Base.metadata.schema


def upgrade() -> None:
    op.add_column(
        "test_execution",
        sa.Column("documents_traites", sa.Integer(), nullable=False, server_default="0"),
        schema=SCHEMA,
    )
    # Les passages deja termines ont traite tous leurs documents compares.
    table = f'"{SCHEMA}".test_execution' if SCHEMA else "test_execution"
    op.execute(f"UPDATE {table} SET documents_traites = documents_compared")
    op.alter_column(
        "test_execution",
        "status",
        existing_type=sa.String(),
        comment="PENDING, RUNNING, COMPLETED, FAILED, CANCELLED",
        existing_comment="PENDING, RUNNING, COMPLETED, FAILED",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.alter_column(
        "test_execution",
        "status",
        existing_type=sa.String(),
        comment="PENDING, RUNNING, COMPLETED, FAILED",
        existing_comment="PENDING, RUNNING, COMPLETED, FAILED, CANCELLED",
        schema=SCHEMA,
    )
    op.drop_column("test_execution", "documents_traites", schema=SCHEMA)
