"""add INGESTED and ERROR to DocumentStatus

Deux valeurs ajoutees a DocumentStatus.

INGESTED s'intercale entre RECEIVED et IN_PROGRESS : il marque le moment ou les
images du document ont ete generees et ou la pre-alimentation OCR peut
commencer. Sans lui, PrepopulationWorker ne peut pas distinguer un document
tout juste recu d'un document dont les pages sont pretes, les deux portant
RECEIVED.

ERROR sort un document de la chaine apres un echec bloquant, plutot que de le
laisser dans un statut qui le ferait repoller indefiniment.

document.status est un VARCHAR simple, comme toutes les colonnes d'enumeration
du schema : il n'y a ni type ENUM PostgreSQL a alterer, ni contrainte CHECK a
mettre a jour. Cette migration est donc de tracabilite, et son upgrade ne touche
aucune donnee.

Le downgrade, lui, doit en toucher : laisser des lignes porter une valeur que
l'enumeration ne connait plus casserait toute lecture. Les documents INGESTED
reviennent a RECEIVED, l'etape precedente, ou le pipeline d'images les reprendra.
Les documents ERROR reviennent eux aussi a RECEIVED : c'est le seul statut d'ou
la chaine peut repartir, au prix d'un retraitement de documents connus comme
echoues.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Aucune donnee a convertir : les deux valeurs sont nouvelles, aucune ligne
    # existante ne peut les porter.
    pass


def downgrade() -> None:
    op.execute(
        """
        UPDATE document
        SET status = 'RECEIVED'
        WHERE status IN ('INGESTED', 'ERROR')
        """
    )
