"""add ingested and error documentstatus

Revision ID: d4e5f6a7b8c9
Revises: b2c3d4e5f6a7
Create Date: 2026-08-06 15:38:38.555084+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Aucune donnee a convertir : les deux valeurs sont nouvelles, aucune ligne
    # existante ne peut les porter.
    pass


def downgrade() -> None:
    op.execute("""
        UPDATE document 
        SET status = 'RECEIVED' 
        WHERE status IN ('INGESTED', 'ERROR')
        """)
