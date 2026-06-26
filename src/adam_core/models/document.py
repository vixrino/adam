"""Table DOCUMENT : Document au sein d'un dataset."""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.enums.status import DocumentStatus


class Document(Base):
    __tablename__ = "document"
    __table_args__ = (Index("ix_document_file_id", "file_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dataset.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("file.id", ondelete="RESTRICT"), nullable=False
    )
    file_name: Mapped[str] = mapped_column(String, nullable=False)
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default=DocumentStatus.RECEIVED.value)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="documents", lazy="noload")
    file: Mapped["File"] = relationship("File", back_populates="documents", lazy="noload")
    document_fields: Mapped[list["DocumentField"]] = relationship(
        "DocumentField", back_populates="document", lazy="noload", cascade="all, delete-orphan"
    )
    ocr_results: Mapped[list["OcrResult"]] = relationship(
        "OcrResult", back_populates="document", lazy="noload", cascade="all, delete-orphan"
    )
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="document", lazy="noload")

    def __repr__(self) -> str:
        return f"<Document id={self.id} file_name={self.file_name!r} status={self.status!r}>"
