"""Table SCHEMA_PAGE : description de chaque page d'un DOC_SCHEMA.

Le schema dit quels champs porte chaque page ; il ne disait pas a quoi une
page ressemble. Or c'est ce qu'il faut pour reconnaitre une page a son
contenu plutot qu'a son rang dans le PDF, et la remettre a sa place quand le
document a ete scanne dans le desordre. Chaque ligne decrit une page par ses
titres de rubrique imprimes, tels qu'un lecteur les voit. Les pages sans
champs (notice, avertissement) y figurent aussi : les reconnaitre distingue
une page deplacee d'une page etrangere au formulaire.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from adam_core.db.base import Base
from adam_core.db.scoping import (
    OrganisationScoped,
    ProjectScoped,
    member_schema_ids,
    org_schema_ids,
)

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class SchemaPage(OrganisationScoped, ProjectScoped, Base):
    __tablename__ = "schema_page"
    __table_args__ = (
        UniqueConstraint("schema_id", "page_number", name="uq_schema_page_schema_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("doc_schema.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, comment="1-indexe")
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Titres de rubrique imprimes, qui servent a reconnaitre la page",
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

    schema: Mapped["DocSchema"] = relationship(  # type: ignore[name-defined]
        "DocSchema",
        back_populates="pages",
        lazy="noload",
    )

    @classmethod
    def __organisation_filter__(cls, organisation_id: int) -> "ColumnElement[bool]":
        # schema_page -> doc_schema -> project -> organisation
        return cls.schema_id.in_(org_schema_ids(organisation_id))

    @classmethod
    def __project_filter__(cls, matricule: str) -> "ColumnElement[bool]":
        # schema_page -> doc_schema -> project (adhesions de l'appelant)
        return cls.schema_id.in_(member_schema_ids(matricule))

    def __repr__(self) -> str:
        return f"<SchemaPage schema_id={self.schema_id} page={self.page_number}>"
