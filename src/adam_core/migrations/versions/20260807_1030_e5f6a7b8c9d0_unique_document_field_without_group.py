"""unique document_field without group

Ferme un trou de la contrainte uq_document_field_doc_spec_group, qui porte sur
(document_id, field_spec_id, group_id).

PostgreSQL considere deux NULL comme distincts dans une contrainte d'unicite :
un champ non repetable, dont le group_id est nul, peut donc etre insere autant
de fois qu'on veut sans que la base proteste. Or c'est le cas courant. La
contrainte ne protege en pratique que les champs repetables.

L'idempotence de POST /documents/{id}/fields/bulk repose donc entierement sur la
verification applicative de create_bulk, qui lit les triplets existants avant
d'inserer. Elle est correcte, mais sans filet : deux appels concurrents sur le
meme document liraient tous deux une table vide et inseraient tous deux, la base
n'ayant aucune raison de les departager.

Cet index unique partiel couvre exactement le cas laisse ouvert, sans toucher a
la contrainte existante qui garde son role pour les champs repetables.

Reprise de donnees
------------------
La creation de l'index echoue si des doublons existent deja. Ils sont donc
supprimes avant, en gardant la ligne la plus ancienne de chaque groupe : c'est
elle que l'OCR a produite en premier, et les suivantes sont des rejeux qui
n'apportent rien. Sur une base saine, cette requete ne touche aucune ligne.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_document_field_doc_spec_no_group"


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM document_field a
        USING document_field b
        WHERE a.group_id IS NULL
          AND b.group_id IS NULL
          AND a.document_id = b.document_id
          AND a.field_spec_id = b.field_spec_id
          AND a.id > b.id
        """
    )
    op.create_index(
        INDEX_NAME,
        "document_field",
        ["document_id", "field_spec_id"],
        unique=True,
        postgresql_where=sa.text("group_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="document_field")
