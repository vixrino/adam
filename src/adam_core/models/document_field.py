"""Table DOCUMENT_FIELD : état livré d'un champ sur un document.

Contrainte unique sur (document_id, field_spec_id, group_id)
"""

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
        UniqueConstraint(
            "document_id",
            "field_spec_id",
            "group_id",
            name="uq_document_field_doc_spec_group",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_spec_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("field_spec.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    group_id: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
        comment="Identifiant de groupe pour les champs répétables",
    )
    # Valeur brute OCR
    ocr_value: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
        comment="Valeur brute extraite par l'OCR lors de la pré-alimentation",
    )
    # Valeur résolue après validation
    resolved_value: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
        comment="Valeur finale validée, mise à jour à chaque proposition acceptée",
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=DocumentFieldStatus.PENDING.value,
    )
    ocr_confidence: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Score de confiance OCR entre 0 et 1",
    )
    consensus_reached: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True = consensus atteint sur ce champ",
    )
    # Polygone OCR : 8 floats [x1,y1,x2,y2,x3,y3,x4,y4]
    ocr_polygon: Mapped[Optional[List[float]]] = mapped_column(
        ARRAY(Float),
        nullable=True,
        comment="Zone détectée par l'OCR : 4 points (x1,y1,...,x4,y4)",
    )
    # Référence à la dernière FIELD_PROPOSAL ayant fixé resolved_value
    resolved_by: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
        comment="ID de la dernière FIELD_PROPOSAL ou 'ocr_system'",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    document: Mapped["Document"] = relationship(  # type: ignore[name-defined]
        "Document",
        back_populates="document_fields",
        lazy="noload",
    )
    field_spec: Mapped["FieldSpec"] = relationship(  # type: ignore[name-defined]
        "FieldSpec",
        back_populates="document_fields",
        lazy="noload",
    )
    field_proposals: Mapped[list["FieldProposal"]] = relationship(  # type: ignore[name-defined]
        "FieldProposal",
        back_populates="document_field",
        lazy="noload",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        polygon_info = f"{len(self.ocr_polygon)} pts" if self.ocr_polygon else "no polygon"
        return (
            f"<DocumentField id={self.id} "
            f"document_id={self.document_id} "
            f"field_spec_id={self.field_spec_id} "
            f"group={self.group_id!r} "
            f"status={self.status!r} "
            f"ocr_value={self.ocr_value!r} "
            f"resolved_value={self.resolved_value!r} "
            f"confidence={self.ocr_confidence} "
            f"consensus={self.consensus_reached} "
            f"polygon={polygon_info}>"
        )
