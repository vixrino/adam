"""Table DOCUMENT_PROGRESS : avancement constate d'un document.

Modele de lecture, alimente exclusivement par DocumentProgressWorker. Aucune
route ne l'ecrit : ses colonnes sont des comptages derives de document, file,
ocr_result, document_field et job, recalcules a chaque passage du worker.

Pourquoi une table plutot qu'un calcul a la volee
--------------------------------------------------
Repondre "ou en est ce document" demande quatre agregats sur des tables
differentes. Le faire dans la route coute ces quatre requetes par document
affiche, ce qui ne tient pas sur une liste de dataset. La table porte le
resultat, la fraicheur etant bornee par l'intervalle de polling du worker.

C'est un cache, pas une source de verite : `computed_at` en donne l'age, et
supprimer toutes ses lignes n'a d'autre effet que de forcer un recalcul.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.db.scoping import (
    OrganisationScoped,
    ProjectScoped,
    member_document_ids,
    org_document_ids,
)
from adam_core.enums.status import DocumentStage

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class DocumentProgress(OrganisationScoped, ProjectScoped, Base):
    __tablename__ = "document_progress"

    # document_id est la cle primaire : un document a un avancement et un seul.
    # La contrainte d'unicite est donc structurelle, le worker s'appuyant dessus
    # pour son upsert (ON CONFLICT DO UPDATE).
    document_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document.id", ondelete="CASCADE"),
        primary_key=True,
    )
    stage: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
        comment="Etape atteinte, cf. DocumentStage",
    )

    # --- Constats binaires -------------------------------------------------
    pdf_received: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="La ligne FILE du document existe",
    )
    pages_rendered: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="FILE.page_count est renseigne : PageImageWorker est passe",
    )
    ocr_available: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Un OcrResult existe pour ce document",
    )

    # --- Comptages ---------------------------------------------------------
    fields_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fields_filled: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Champs portant une valeur OCR ou resolue",
    )
    fields_validated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_submitted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_required: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="DATASET.required_operators au moment du calcul",
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        # Indexe : le worker selectionne ses candidats par anciennete de calcul
        # a chaque cycle, sans index c'est un seq scan sur toute la table.
        index=True,
        comment="Date du dernier recalcul : age de la mesure",
    )

    document: Mapped["Document"] = relationship(  # type: ignore[name-defined]
        "Document",
        back_populates="progress",
        lazy="noload",
    )

    @property
    def fields_completion(self) -> Optional[float]:
        """Part des champs renseignes, ou None si le document n'en attend aucun."""
        if self.fields_total == 0:
            return None
        return self.fields_filled / self.fields_total

    @classmethod
    def __organisation_filter__(cls, organisation_id: int) -> "ColumnElement[bool]":
        # document_progress -> document -> dataset -> project -> organisation
        return cls.document_id.in_(org_document_ids(organisation_id))

    @classmethod
    def __project_filter__(cls, matricule: str) -> "ColumnElement[bool]":
        # document_progress -> document -> dataset -> project (adhesions)
        return cls.document_id.in_(member_document_ids(matricule))

    def __repr__(self) -> str:
        return (
            f"<DocumentProgress document_id={self.document_id} stage={self.stage!r} "
            f"fields={self.fields_filled}/{self.fields_total} "
            f"jobs={self.jobs_submitted}/{self.jobs_required}>"
        )
