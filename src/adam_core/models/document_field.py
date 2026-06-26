"""Table DOCUMENT_FIELD : etat d'un champ sur un document."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.enums.status import DocumentFieldStatus


class DocumentField(Base):
    __tablename__ = "document_field"
    __table_args__ = (
        UniqueConstraint("document_id", "field_spec_id", "group_id", name="uq_document_field_doc_spec_group"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("document.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_spec_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("field_spec.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    group_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    ocr_value: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    resolved_value: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default=DocumentFieldStatus.PENDING.value)
    ocr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    consensus_reached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ocr_polygon: Mapped[Optional[list[float]]] = mapped_column(ARRAY(Float), nullable=True)
    resolved_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    document: Mapped["Document"] = relationship("Document", back_populates="document_fields", lazy="noload")
    field_spec: Mapped["FieldSpec"] = relationship("FieldSpec", back_populates="document_fields", lazy="noload")
    field_proposals: Mapped[list["FieldProposal"]] = relationship(
        "FieldProposal", back_populates="document_field", lazy="noload", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        polygon_info = f"{len(self.ocr_polygon)} pts" if self.ocr_polygon else "no polygon"
        return (
            f"<DocumentField id={self.id} document_id={self.document_id} "
            f"field_spec_id={self.field_spec_id} group={self.group_id!r} "
            f"status={self.status!r} ocr_polygon={polygon_info}>"
        )
