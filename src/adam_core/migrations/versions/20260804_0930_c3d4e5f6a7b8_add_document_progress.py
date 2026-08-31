"""add document_progress

Table d'avancement constate, alimentee par DocumentProgressWorker.

document_id est a la fois cle primaire et cle etrangere : un document a un
avancement et un seul, et la contrainte d'unicite necessaire a l'upsert du
worker (ON CONFLICT DO UPDATE) est donc structurelle plutot qu'ajoutee.

Le ON DELETE CASCADE est volontaire, contrairement au RESTRICT des autres FK du
schema : cette table est un cache derive, la perdre avec son document n'entraine
aucune perte d'information. Le worker la reconstruit.

Aucune reprise de donnees : les lignes apparaissent au premier passage du
worker, qui prend en charge les documents depourvus de progression.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_progress",
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("pdf_received", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("pages_rendered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ocr_available", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("fields_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fields_filled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fields_validated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_submitted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_required", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Contraintes nommees explicitement selon NAMING_CONVENTION (db/base.py).
        # Le schema etant cree par create_all dans les environnements neufs et
        # par ces migrations dans les bases existantes, un nom laisse a Postgres
        # divergerait entre les deux.
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            ondelete="CASCADE",
            name="fk_document_progress_document_id_document",
        ),
        sa.PrimaryKeyConstraint("document_id", name="pk_document_progress"),
    )
    op.create_index("ix_document_progress_stage", "document_progress", ["stage"])
    # Le worker balaye par anciennete de calcul a chaque cycle : sans cet index,
    # la selection des candidats est un seq scan sur toute la table.
    op.create_index("ix_document_progress_computed_at", "document_progress", ["computed_at"])


def downgrade() -> None:
    op.drop_index("ix_document_progress_computed_at", table_name="document_progress")
    op.drop_index("ix_document_progress_stage", table_name="document_progress")
    op.drop_table("document_progress")
