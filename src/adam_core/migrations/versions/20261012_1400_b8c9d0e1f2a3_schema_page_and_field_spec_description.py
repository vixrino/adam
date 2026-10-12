"""schema_page and field_spec.description

Rend l'extraction OCR generique : le connecteur lisait les champs et les
pages d'un module Python fige pour le CERFA (cerfa_v2). Il les lit desormais
du schema en base.

- schema_page : une ligne par page d'un schema, decrite par ses titres de
  rubrique imprimes, pour reconnaitre une page a son contenu et remettre en
  ordre un document scanne dans le desordre ;
- field_spec.description : ce que le champ contient, dit au moteur
  d'extraction. Cote nota, la colonne existe deja (289059f04c71) : seule la
  table schema_page y est a creer.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("field_spec", sa.Column("description", sa.Text(), nullable=True))
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
    op.drop_column("field_spec", "description")
