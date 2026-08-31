"""Table JOB : tâche de labellisation par opérateur."""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.db.scoping import OrganisationScoped, org_dataset_ids
from adam_core.enums.status import JobState, JobStep

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class Job(OrganisationScoped, Base):
    __tablename__ = "job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("dataset.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    state: Mapped[str] = mapped_column(String, nullable=False, default=JobState.ASSIGNED.value)
    step: Mapped[str] = mapped_column(String, nullable=False, default=JobStep.VALIDATION.value)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    dataset: Mapped["Dataset"] = relationship(  # type: ignore[name-defined]
        "Dataset",
        back_populates="jobs",
        lazy="noload",
    )
    document: Mapped["Document"] = relationship(  # type: ignore[name-defined]
        "Document",
        back_populates="jobs",
        lazy="noload",
    )
    agent: Mapped["User"] = relationship(  # type: ignore[name-defined]
        "User",
        foreign_keys=[agent_id],
        back_populates="jobs",
        lazy="noload",
    )
    field_proposals: Mapped[list["FieldProposal"]] = relationship(  # type: ignore[name-defined]
        "FieldProposal",
        back_populates="job",
        lazy="noload",
        cascade="all, delete-orphan",
    )

    @classmethod
    def __organisation_filter__(cls, organisation_id: int) -> "ColumnElement[bool]":
        # job -> dataset -> project -> organisation
        return cls.dataset_id.in_(org_dataset_ids(organisation_id))

    def __repr__(self) -> str:
        return (
            f"<Job id={self.id} step={self.step!r} state={self.state!r} "
            f"agent_id={self.agent_id}>"
        )
