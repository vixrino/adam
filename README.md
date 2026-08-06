# ADAM - Annotation et Données Automatisées
uv run alembic -c src/nota_core/alembic.ini revision -m "add ingested and error documentstatus" --rev-id d4e5f6a7b8c9

Ouvre le fichier créé et remplace les deux fonctions par :

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

Vérifie que from alembic import op est bien dans les imports — Alembic le met par défaut, mais certains modèles de fichier ne l'ajoutent que si sqlalchemy as sa est utilisé. Ne touche pas à l'en-tête (revision, down_revision).

Puis :

uv run alembic -c src/nota_core/alembic.ini heads
uv run alembic -c src/nota_core/alembic.ini upgrade head
uv run alembic -c src/nota_core/alembic.ini current
