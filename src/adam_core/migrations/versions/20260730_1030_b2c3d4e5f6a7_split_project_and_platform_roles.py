"""split project and platform roles

Aligne le modele de roles sur le RACI NOTA, qui distingue quatre acteurs la ou
l'enumeration n'en portait que trois.

Deux changements de schema
--------------------------
1. Ajout de ``user.platform_role`` (VARCHAR NULL, indexe) : role transverse
   parmi PlatformRole {NOTA_SUPERVISOR, NOTA_ADMIN}, NULL pour un utilisateur
   purement metier.
2. ``user_project.role`` ne porte plus que ProjectRole {OPERATOR,
   BUSINESS_ADMIN}. La colonne reste un VARCHAR simple, sans type ENUM
   PostgreSQL a alterer, comme les autres colonnes d'enumeration du schema.

Conversion des donnees
----------------------
ADMIN designait l'Administrateur Metier dans un contexte de projet : les lignes
concernees passent a BUSINESS_ADMIN.

SUPERVISOR designait un role transverse stocke a tort sur une adhesion a un
projet. Pour chaque ligne, ``user.platform_role`` est positionne a
NOTA_SUPERVISOR, puis l'adhesion est supprimee : un role de plateforme n'a pas de
sens rattache a un projet, et la conserver en la retrogradant a OPERATOR
accorderait au superviseur des droits d'annotation que le RACI lui refuse
explicitement (Annoter les donnees : R pour l'Operateur Metier, I pour le
Superviseur NOTA).

Le downgrade restaure les adhesions supprimees a l'identique, l'information
necessaire etant conservee dans platform_role avant l'effacement de la colonne.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("platform_role", sa.String(), nullable=True))
    op.create_index("ix_user_platform_role", "user", ["platform_role"])

    # 1. Les superviseurs deviennent porteurs d'un role de plateforme.
    op.execute("""
        UPDATE "user"
        SET platform_role = 'NOTA_SUPERVISOR'
        WHERE id IN (
            SELECT user_id FROM user_project WHERE role = 'SUPERVISOR'
        )
        """)
    # 2. Leur adhesion au projet perd son objet (cf. docstring du module).
    op.execute("DELETE FROM user_project WHERE role = 'SUPERVISOR'")
    # 3. ADMIN valait Administrateur Metier dans un contexte de projet.
    op.execute("UPDATE user_project SET role = 'BUSINESS_ADMIN' WHERE role = 'ADMIN'")


def downgrade() -> None:
    op.execute("UPDATE user_project SET role = 'ADMIN' WHERE role = 'BUSINESS_ADMIN'")

    # Restaure une adhesion SUPERVISOR sur les projets de l'organisation du
    # superviseur : c'est la seule reconstruction possible, l'adhesion d'origine
    # ne portant aucune autre information que le couple (user, project).
    op.execute("""
        INSERT INTO user_project (user_id, project_id, role, created_at, updated_at)
        SELECT u.id, p.id, 'SUPERVISOR', now(), now()
        FROM "user" u
        JOIN project p ON p.organisation_id = u.organisation_id
        WHERE u.platform_role = 'NOTA_SUPERVISOR'
        ON CONFLICT (user_id, project_id) DO NOTHING
        """)

    op.drop_index("ix_user_platform_role", table_name="user")
    op.drop_column("user", "platform_role")
