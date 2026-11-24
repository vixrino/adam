"""Tables EXPORT et EXPORT_DOCUMENT : livraison d'un dataset.

Un export fige, en un seul JSON (`extractions`), les extractions de tous les
documents retenus. EXPORT_DOCUMENT dit quels documents il couvre et lesquels
servent de jeu au test automatise (`in_test`).

Retention : tant que `released_at` est NULL l'export est « ligne » et les
fichiers PVC de ses documents ne doivent pas etre purges.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, deferred, mapped_column

from adam_core.db.base import Base
from adam_core.db.scoping import (
    OrganisationScoped,
    ProjectScoped,
    member_dataset_ids,
    org_dataset_ids,
)
from adam_core.enums.status import ExportStatus

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class Export(OrganisationScoped, ProjectScoped, Base):
    __tablename__ = "export"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("dataset.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=ExportStatus.IN_PROGRESS.value,
    )
    # Differe : lister les exports ne doit pas charger le JSON, enorme.
    extractions: Mapped[Optional[dict[str, Any]]] = deferred(
        mapped_column(
            JSONB,
            nullable=True,
            comment="Extractions de tous les documents de l'export, en un seul JSON",
        )
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="NULL = export ligne : les fichiers PVC de ses documents sont retenus",
    )

    @classmethod
    def __organisation_filter__(cls, organisation_id: int) -> "ColumnElement[bool]":
        return cls.dataset_id.in_(org_dataset_ids(organisation_id))

    @classmethod
    def __project_filter__(cls, matricule: str) -> "ColumnElement[bool]":
        return cls.dataset_id.in_(member_dataset_ids(matricule))


class ExportDocument(OrganisationScoped, ProjectScoped, Base):
    """Document couvert par un export ; `in_test` = retenu pour le test automatise."""

    __tablename__ = "export_document"

    export_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("export.id", ondelete="CASCADE"),
        primary_key=True,
    )
    # RESTRICT : un document dans un export ligne ne se supprime pas sans decision explicite.
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,  # « dans quels exports est ce document ? » (purge PVC)
    )
    in_test: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Document retenu pour le jeu du test automatise",
    )

    @classmethod
    def __organisation_filter__(cls, organisation_id: int) -> "ColumnElement[bool]":
        return cls.export_id.in_(
            select(Export.id).where(Export.dataset_id.in_(org_dataset_ids(organisation_id)))
        )

    @classmethod
    def __project_filter__(cls, matricule: str) -> "ColumnElement[bool]":
        return cls.export_id.in_(
            select(Export.id).where(Export.dataset_id.in_(member_dataset_ids(matricule)))
        )
