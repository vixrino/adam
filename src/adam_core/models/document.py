"""Table DOCUMENT : document au sein d'un dataset.

Index sur file_id pour la vérification des références avant purge PVC.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.db.scoping import (
    OrganisationScoped,
    ProjectScoped,
    member_dataset_ids,
    org_dataset_ids,
)
from adam_core.enums.status import DocumentStatus

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class Document(OrganisationScoped, ProjectScoped, Base):
    __tablename__ = "document"

    __table_args__ = (
        # Index explicite pour purge PVC
        Index("ix_document_file_id", "file_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("dataset.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("file.id", ondelete="RESTRICT"),
        nullable=False,
        # index géré par __table_args__ ci-dessus
    )
    file_name: Mapped[str] = mapped_column(
        String,
        nullable=False,
        comment="Nom de fichier original reçu",
    )
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata",  # nom de colonne en BDD
        JSONB,
        nullable=True,
        comment="Métadonnées libres d'ingestion : source, lot, date de dépôt...",
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=DocumentStatus.RECEIVED.value,
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
    dataset: Mapped["Dataset"] = relationship(  # type: ignore[name-defined]
        "Dataset",
        back_populates="documents",
        lazy="noload",
    )
    file: Mapped["File"] = relationship(  # type: ignore[name-defined]
        "File",
        back_populates="documents",
        lazy="noload",
    )
    document_fields: Mapped[list["DocumentField"]] = relationship(  # type: ignore[name-defined]
        "DocumentField",
        back_populates="document",
        lazy="noload",
        cascade="all, delete-orphan",
    )
    ocr_results: Mapped[list["OcrResult"]] = relationship(  # type: ignore[name-defined]
        "OcrResult",
        back_populates="document",
        lazy="noload",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list["Job"]] = relationship(  # type: ignore[name-defined]
        "Job",
        back_populates="document",
        lazy="noload",
    )
    # Avancement constate, recalcule par DocumentProgressWorker. uselist=False :
    # la cle primaire de document_progress est document_id, donc au plus une
    # ligne. Supprime avec le document, ce n'est qu'un cache.
    progress: Mapped[Optional["DocumentProgress"]] = relationship(  # type: ignore[name-defined]
        "DocumentProgress",
        back_populates="document",
        lazy="noload",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def page_count(self) -> Optional[int]:
        """Nombre de pages du fichier associé.

        Retourne None si la relation file n'a pas été chargée (lazy='noload').
        Utiliser selectinload(Document.file) pour peupler cette valeur.
        """
        f = self.__dict__.get("file")
        return f.page_count if f is not None else None

    @classmethod
    def __organisation_filter__(cls, organisation_id: int) -> "ColumnElement[bool]":
        # document -> dataset -> project -> organisation
        return cls.dataset_id.in_(org_dataset_ids(organisation_id))

    @classmethod
    def __project_filter__(cls, matricule: str) -> "ColumnElement[bool]":
        # document -> dataset -> project (adhesions de l'appelant)
        return cls.dataset_id.in_(member_dataset_ids(matricule))

    def __repr__(self) -> str:
        return f"<Document id={self.id} file_name={self.file_name!r} status={self.status!r}>"
