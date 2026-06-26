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
        UniqueConstraint("schema_id", "section_id", "group_id", "field_key", name="uq_field_spec_schema_group_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doc_schema.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    section_id: Mapped[str] = mapped_column(String, nullable=False)
    section_label: Mapped[str] = mapped_column(String, nullable=False)
    group_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    field_key: Mapped[str] = mapped_column(String, nullable=False)
    display_label: Mapped[str] = mapped_column(String, nullable=False)
    value_type: Mapped[str] = mapped_column(String, nullable=False, default=FieldValueType.TEXT.value)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    polygon: Mapped[Optional[List[float]]] = mapped_column(ARRAY(Float), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    schema: Mapped["DocSchema"] = relationship("DocSchema", back_populates="field_specs", lazy="noload")
    document_fields: Mapped[list["DocumentField"]] = relationship(
        "DocumentField", back_populates="field_spec", lazy="noload"
    )

    def __repr__(self) -> str:
        polygon_info = f"({len(self.polygon)}) pts" if self.polygon else "no polygon"
        return f"<FieldSpec id={self.id} key={self.field_key!r} page={self.page} polygon={polygon_info}>"
