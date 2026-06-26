"""add RECEIVED documentstatus

Sprint 3 - ingestion PDF.

CA-6 du ticket d'ingestion PDF : ajouter le statut RECEIVED a l'enum
DocumentStatus "si absent". Constat : la colonne ``document.status`` est
un ``String`` simple (pas un type ENUM PostgreSQL), et la valeur
``RECEIVED`` est deja presente dans ``DocumentStatus``. Aucune
modification de schema n'est donc requise ; cette revision est un no-op
documente, conserve pour la tracabilite de la chaine Alembic.
"""

from typing import Sequence, Union

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "65a5fd7b662f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # status est un VARCHAR : aucune contrainte d'enum a alterer.
    pass


def downgrade() -> None:
    pass
