"""test recipes data model

Revision ID: 3e695d259679
Revises: b2c3d4e5f6a7
Create Date: 2026-08-20 13:42:10.248746+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "3e695d259679"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "field_spec",
        sa.Column(
            "is_sensitive",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="Donnee personnelle sensible : pilote le stockage des comparaisons",
        ),
    )

    op.create_table(
        "test_recipe",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("document_ids", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["dataset_id"], ["dataset.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "name", name="uq_test_recipe_dataset_name"),
    )
    op.create_index("ix_test_recipe_dataset_id", "test_recipe", ["dataset_id"])
    op.create_index("ix_test_recipe_created_by_user_id", "test_recipe", ["created_by_user_id"])

    op.create_table(
        "test_execution",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("ocr_provider", sa.String(), nullable=False),
        sa.Column("ocr_model_id", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("documents_compared", sa.Integer(), nullable=False),
        sa.Column("fields_compared", sa.Integer(), nullable=False),
        sa.Column("fields_human_verified", sa.Integer(), nullable=False),
        sa.Column("diff_count", sa.Integer(), nullable=False),
        sa.Column("unexpected_count", sa.Integer(), nullable=False),
        sa.Column("ocr_calls_made", sa.Integer(), nullable=False),
        sa.Column("pages_processed", sa.Integer(), nullable=False),
        sa.Column("confidence_histogram", postgresql.JSONB(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["recipe_id"], ["test_recipe.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_test_execution_recipe_id", "test_execution", ["recipe_id"])
    op.create_index("ix_test_execution_status", "test_execution", ["status"])
    op.create_index(
        "ix_test_execution_created_by_user_id", "test_execution", ["created_by_user_id"]
    )

    op.create_table(
        "comparison_result",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("execution_id", sa.Integer(), nullable=False),
        sa.Column("document_field_id", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.Column("diff_kind", sa.String(), nullable=True),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("expected_value", sa.String(), nullable=True),
        sa.Column("observed_value", sa.String(), nullable=True),
        sa.Column("observed_hmac", sa.String(), nullable=True),
        sa.Column("edit_distance", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["execution_id"], ["test_execution.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_field_id"], ["document_field.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "execution_id", "document_field_id", name="uq_comparison_result_execution_field"
        ),
    )
    op.create_index("ix_comparison_result_execution_id", "comparison_result", ["execution_id"])
    op.create_index(
        "ix_comparison_result_document_field_id", "comparison_result", ["document_field_id"]
    )

    op.create_table(
        "evaluation_report",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("execution_id", sa.Integer(), nullable=False),
        sa.Column("field_spec_id", sa.Integer(), nullable=False),
        sa.Column("field_key", sa.String(), nullable=False),
        sa.Column("compared", sa.Integer(), nullable=False),
        sa.Column("diff_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["test_execution.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["field_spec_id"], ["field_spec.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "execution_id", "field_spec_id", name="uq_evaluation_report_execution_field_spec"
        ),
    )
    op.create_index("ix_evaluation_report_execution_id", "evaluation_report", ["execution_id"])
    op.create_index("ix_evaluation_report_field_spec_id", "evaluation_report", ["field_spec_id"])


def downgrade() -> None:
    op.drop_table("evaluation_report")
    op.drop_table("comparison_result")
    op.drop_table("test_execution")
    op.drop_table("test_recipe")
    op.drop_column("field_spec", "is_sensitive")
