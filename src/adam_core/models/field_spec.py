"""Table FIELD_SPEC : champ individuel au sein d'un DOC_SCHEMA."""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Float

from adam_core.db.base import Base
from adam_core.enums.status import FieldValueType


class FieldSpec(Base):
    __tablename__ = "field_spec"

    __table_args__ = (
        UniqueConstraint(
            "schema_id",
            "section_id",
            "group_id",
            "field_key",
            name="uq_field_spec_schema_group_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("doc_schema.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page: Mapped[int] = mapped_column(Integer, nullable=False)

    # Section
    section_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Identifiant technique de la section",
    )
    section_label: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Libellé de la section",
    )

    # Champ
    group_id: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True,
        comment="Instance de groupe pour les champs répétables",
    )
    field_key: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Clé du champ",
    )
    display_label: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Libellé affiché à l'opérateur",
    )
    value_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=FieldValueType.TEXT.value,
        comment="Type de valeur : TEXT, NUMBER, DATE, DATETIME, BOOLEAN",
    )
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Polygon : 8 floats [x1,y1,x2,y2,x3,y3,x4,y4]
    polygon: Mapped[Optional[List[float]]] = mapped_column(
        ARRAY(Float),
        nullable=True,
        comment="4 points (x1,y1,x2,y2,x3,y3,x4,y4). 8 floats si non null",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    schema: Mapped["DocSchema"] = relationship(  # type: ignore[name-defined]
        "DocSchema",
        back_populates="field_specs",
        lazy="noload",
    )
    document_fields: Mapped[list["DocumentField"]] = relationship(  # type: ignore[name-defined]
        "DocumentField",
        back_populates="field_spec",
        lazy="noload",
    )

    def __repr__(self) -> str:
        polygon_info = f"{len(self.polygon)} pts" if self.polygon else "no polygon"
        return (
            f"<FieldSpec id={self.id} "
            f"key={self.field_key!r} "
            f"label={self.display_label!r} "
            f"type={self.value_type!r} "
            f"page={self.page} "
            f"section_id={self.section_id!r} "
            f"section_label={self.section_label!r} "
            f"group={self.group_id!r} "
            f"required={self.required} "
            f"polygon={polygon_info} "
            f"schema_id={self.schema_id}>"
        )
