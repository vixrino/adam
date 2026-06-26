"""Table DATASET : ensemble de documents à labelliser.

Un dataset regroupe des documents sous un fournisseur OCR et une
configuration partagés. Il est rattaché à un projet et verrouillé à
un schéma de document (1:1 avec DOC_SCHEMA).
"""

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
        Integer,
        ForeignKey("project.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    schema_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("doc_schema.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Schéma verrouillé sur ce dataset",
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ocr_provider: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default=OcrProvider.PULSAR.value,
        comment="Moteur OCR : PULSAR, MISTRAL",
    )
    ocr_model_id: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
        comment="Version du modèle OCR",
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=DatasetStatus.DRAFT.value,
    )
    ocr_job_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Active la pré-alimentation automatique via OCR",
    )
    required_operators: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        comment="Nombre d'opérateurs requis par document",
    )
    # Config provisoire
    configs: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="{...}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    project: Mapped["Project"] = relationship(  # type: ignore[name-defined]
        "Project",
        back_populates="datasets",
        lazy="noload",
    )
    schema: Mapped["DocSchema"] = relationship(  # type: ignore[name-defined]
        "DocSchema",
        back_populates="datasets",
        lazy="noload",
    )
    documents: Mapped[list["Document"]] = relationship(  # type: ignore[name-defined]
        "Document",
        back_populates="dataset",
        lazy="noload",
    )
    jobs: Mapped[list["Job"]] = relationship(  # type: ignore[name-defined]
        "Job",
        back_populates="dataset",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Dataset id={self.id} name={self.name!r} status={self.status!r}>"
