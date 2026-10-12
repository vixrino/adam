"""rename field_spec.is_sensitive to sensitive

Aligne le nom de la colonne sur celui retenu par nota, a la demande de la
revue : le prefixe is_ n'est pas la convention du modele. Renommage pur, sans
reprise de donnees.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = ("c3d4e5f6a7b8", "e5f6a7b8c9d0")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("field_spec", "is_sensitive", new_column_name="sensitive")


def downgrade() -> None:
    op.alter_column("field_spec", "sensitive", new_column_name="is_sensitive")
