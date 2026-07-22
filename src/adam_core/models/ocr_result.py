"""Table OCR_RESULT : réponse JSON brute du moteur OCR.

Un seul résultat OCR par document par dataset.
Contrainte unique sur (document_id, dataset_id).
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.db.scoping import OrganisationScoped, org_dataset_ids
from adam_core.enums.ocr import StorageMode

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class OcrResult(OrganisationScoped, Base):
    __tablename__ = "ocr_result"

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "dataset_id",
            name="uq_ocr_result_document_dataset",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dataset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("dataset.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    storage_mode: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=StorageMode.JSONB.value,
        comment="jsonb = stocké en base, file = stocké sur PVC",
    )
    raw_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Réponse OCR complète. Null si storage_mode=file",
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    document: Mapped["Document"] = relationship(  # type: ignore[name-defined]
        "Document",
        back_populates="ocr_results",
        lazy="noload",
    )

    @classmethod
    def __organisation_filter__(cls, organisation_id: int) -> "ColumnElement[bool]":
        # ocr_result -> dataset -> project -> organisation
        return cls.dataset_id.in_(org_dataset_ids(organisation_id))

    def __repr__(self) -> str:
        return (
            f"<OcrResult id={self.id} document_id={self.document_id} "
            f"mode={self.storage_mode!r}>"
        )
