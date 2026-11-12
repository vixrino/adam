"""empreinte de la verite humaine sur l'export et l'execution de benchmark

Un export fige les documents, pas leurs valeurs : une correction de la verite
entre deux executions changeait le score sans que rien ne le dise.

- dataset_export.verite_empreintes : empreinte de chaque document a l'export ;
- test_execution.verite_hash : empreinte de la verite jugee par l'execution.

Nullables : les exports et executions existants n'en ont pas. Schema nomme
explicitement, comme d0e1f2a3b4c5.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from adam_core.db.base import Base

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = Base.metadata.schema


def upgrade() -> None:
    op.add_column(
        "dataset_export",
        sa.Column("verite_empreintes", postgresql.JSONB(), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        "test_execution", sa.Column("verite_hash", sa.String(), nullable=True), schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_column("test_execution", "verite_hash", schema=SCHEMA)
    op.drop_column("dataset_export", "verite_empreintes", schema=SCHEMA)
