"""Table DOC_SCHEMA : structure d'un type de document.

Définit quels champs existent sur un formulaire, leurs types et positions.
Un schéma est versionné et partagé entre datasets et recettes de test.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base


class DocSchema(Base):
    __tablename__ = "doc_schema"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # FK, le projet owner
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("project.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String, nullable=False)
    document_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Identifiant du type de document",
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
        foreign_keys=[project_id],
        back_populates="schemas",
        lazy="noload",
    )
    field_specs: Mapped[list["FieldSpec"]] = relationship(  # type: ignore[name-defined]
        "FieldSpec",
        back_populates="schema",
        lazy="noload",
        cascade="all, delete-orphan",
    )
    datasets: Mapped[list["Dataset"]] = relationship(  # type: ignore[name-defined]
        "Dataset",
        back_populates="schema",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<DocSchema id={self.id} name={self.name!r} "
            f"document_type={self.document_type!r} version={self.version}>"
        )
