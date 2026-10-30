"""Table TEST_RECIPE : recette d'evaluation du moteur OCR."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from adam_core.db.base import Base
from adam_core.db.scoping import (
    OrganisationScoped,
    ProjectScoped,
    member_dataset_ids,
    org_dataset_ids,
)
from adam_core.enums.status import TestRecipeStatus

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class TestRecipe(OrganisationScoped, ProjectScoped, Base):
    __tablename__ = "test_recipe"

    __test__ = False

    __table_args__ = (UniqueConstraint("dataset_id", "name", name="uq_test_recipe_dataset_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("dataset.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    #: Perimetre fige au verrouillage : ids des documents evalues.
    document_ids: Mapped[List[int]] = mapped_column(ARRAY(Integer), nullable=False)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=TestRecipeStatus.DRAFT.value,
        comment="Cycle de vie : DRAFT, LOCKED, ARCHIVED",
    )
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @classmethod
    def __organisation_filter__(cls, organisation_id: int) -> "ColumnElement[bool]":
        # test_recipe -> dataset -> project -> organisation
        return cls.dataset_id.in_(org_dataset_ids(organisation_id))

    @classmethod
    def __project_filter__(cls, matricule: str) -> "ColumnElement[bool]":
        return cls.dataset_id.in_(member_dataset_ids(matricule))

    def __repr__(self) -> str:
        return (
            f"<TestRecipe id={self.id} name={self.name!r} status={self.status!r} "
            f"documents={len(self.document_ids) if self.document_ids else 0}>"
        )
