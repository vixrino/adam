"""Table JOB : tache de labellisation par operateur."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.enums.status import JobState, JobStep


class Job(Base):
    __tablename__ = "job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dataset.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(String, nullable=False, default=JobState.ASSIGNED.value)
    step: Mapped[str] = mapped_column(String, nullable=False, default=JobStep.VALIDATION.value)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="jobs", lazy="noload")
    document: Mapped["Document"] = relationship("Document", back_populates="jobs", lazy="noload")
    agent: Mapped["User"] = relationship(
        "User", back_populates="jobs", foreign_keys=[agent_id], lazy="noload"
    )
    field_proposals: Mapped[list["FieldProposal"]] = relationship(
        "FieldProposal", back_populates="job", lazy="noload", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Job id={self.id} step={self.step!r} state={self.state!r} agent_id={self.agent_id}>"
