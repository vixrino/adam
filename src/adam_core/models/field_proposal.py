"""Table FIELD_PROPOSAL : journal des propositions de valeur humaines."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.enums.status import FieldValueType, JobStep


class FieldProposal(Base):
    __tablename__ = "field_proposal"
    __table_args__ = (Index("ix_field_proposal_field_step", "document_field_id", "step"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_field_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("document_field.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step: Mapped[str] = mapped_column(String, nullable=False, default=JobStep.VALIDATION.value)
    value_type: Mapped[str] = mapped_column(String, nullable=False, default=FieldValueType.TEXT.value)
    value: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document_field: Mapped["DocumentField"] = relationship(
        "DocumentField", back_populates="field_proposals", lazy="noload"
    )
    job: Mapped["Job"] = relationship("Job", back_populates="field_proposals", lazy="noload")

    def __repr__(self) -> str:
        return f"<FieldProposal id={self.id} field_id={self.document_field_id} step={self.step!r}>"
