"""Table DATASET : ensemble de documents a labelliser."""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.enums.ocr import OcrProvider
from adam_core.enums.status import DatasetStatus


class Dataset(Base):
    __tablename__ = "dataset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("project.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    schema_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doc_schema.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ocr_provider: Mapped[str] = mapped_column(String(128), nullable=False, default=OcrProvider.PULSAR.value)
    ocr_model_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default=DatasetStatus.DRAFT.value)
    ocr_job_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    required_operators: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    configs: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    project: Mapped["Project"] = relationship("Project", back_populates="datasets", lazy="noload")
    schema: Mapped["DocSchema"] = relationship("DocSchema", back_populates="datasets", lazy="noload")
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="dataset", lazy="noload")
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="dataset", lazy="noload")

    def __repr__(self) -> str:
        return f"<Dataset id={self.id} name={self.name!r} status={self.status!r}>"
