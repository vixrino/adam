"""Table DATASET_EXPORT : un lot fige de documents d'un dataset, pour le benchmark.

Un benchmark ne mesure rien de stable sur un dataset en cours de modification :
des documents y entrent, d'autres en sortent. L'export fige, a un instant, la
liste des documents et l'empreinte du schema du dataset ; les recettes de test
partent de la, et deux recettes sur le meme export portent sur les memes
documents, donc se comparent.

La verite terrain n'est pas copiee (meme raison que pour test_recipe : droit a
l'effacement) : elle reste dans document_field. L'export fige le perimetre, pas
les valeurs.

``schema_hash`` est l'empreinte du schema au moment de l'export, calculee comme
celle du worker (benchmark/schema.py) : une execution dont le schema a change
depuis le signale. ``verite_empreintes`` fait de meme pour la verite humaine,
document par document (benchmark/verite.py) : les valeurs ne sont pas copiees,
mais une correction faite depuis l'export se voit.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from adam_core.db.base import Base
from adam_core.db.scoping import (
    OrganisationScoped,
    ProjectScoped,
    member_dataset_ids,
    org_dataset_ids,
)

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class DatasetExport(OrganisationScoped, ProjectScoped, Base):
    __tablename__ = "dataset_export"

    __table_args__ = (
        UniqueConstraint("dataset_id", "name", name="uq_dataset_export_dataset_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("dataset.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    schema_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("doc_schema.id", ondelete="RESTRICT"), nullable=False
    )
    schema_hash: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    #: Les documents figes, comme test_recipe.document_ids : un ARRAY plutot
    #: qu'une table de liaison.
    document_ids: Mapped[List[int]] = mapped_column(ARRAY(Integer), nullable=False)
    #: {document_id (en texte, cle JSON): empreinte de sa verite a l'export}.
    #: Nul pour un export cree avant que l'empreinte existe.
    verite_empreintes: Mapped[Optional[Dict[str, str]]] = mapped_column(JSONB, nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @classmethod
    def __organisation_filter__(cls, organisation_id: int) -> "ColumnElement[bool]":
        # dataset_export -> dataset -> project -> organisation
        return cls.dataset_id.in_(org_dataset_ids(organisation_id))

    @classmethod
    def __project_filter__(cls, matricule: str) -> "ColumnElement[bool]":
        return cls.dataset_id.in_(member_dataset_ids(matricule))

    def __repr__(self) -> str:
        return (
            f"<DatasetExport id={self.id} dataset_id={self.dataset_id} "
            f"documents={len(self.document_ids or [])}>"
        )
