"""add schema_page

Extraction OCR generique : chaque page d'un schema est decrite par ses
titres de rubrique imprimes, pour reconnaitre une page a son contenu et
remettre en ordre un document scanne dans le desordre.
field_spec.description est ajoutee si elle manque : elle existe deja la
ou la migration 289059f04c71 est passee.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9ce8e7d8cc0c"
down_revision: Union[str, None] = "c110111f97cd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE field_spec ADD COLUMN IF NOT EXISTS description TEXT")
    op.create_table(
        "schema_page",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "schema_id",
            sa.Integer(),
            sa.ForeignKey("doc_schema.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False, comment="1-indexe"),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            comment="Titres de rubrique imprimes, qui servent a reconnaitre la page",
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("schema_id", "page_number", name="uq_schema_page_schema_number"),
    )
    op.create_index("ix_schema_page_schema_id", "schema_page", ["schema_id"])


def downgrade() -> None:
    op.drop_index("ix_schema_page_schema_id", table_name="schema_page")
    op.drop_table("schema_page")
