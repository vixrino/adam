"""split project and platform roles

Revision ID: b2c3d4e5f6a7
Revises: 8181acde63d8
Create Date: 2026-08-03 08:43:22.375749+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "8181acde63d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("platform_role", sa.String(), nullable=True))
    op.create_index("ix_user_platform_role", "user", ["platform_role"])

    op.execute("""
        UPDATE "user" u
        SET platform_role = 'NOTA_SUPERVISOR'
        WHERE EXISTS (
            SELECT 1
            FROM user_project up
            WHERE up.user_id = u.id
              AND up.role = 'SUPERVISOR'
        )
    """)

    op.execute("UPDATE user_project SET role = 'BUSINESS_ADMIN' WHERE role = 'ADMIN'")
    op.execute("DELETE FROM user_project WHERE role = 'SUPERVISOR'")


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
