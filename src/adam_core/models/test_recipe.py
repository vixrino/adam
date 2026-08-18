"""Table TEST_RECIPE : recette d'evaluation du moteur OCR.

Une recette designe un perimetre fige de documents d'un dataset, contre lequel
les executions successives comparent la sortie du moteur. La verite terrain
n'est PAS copiee ici : elle vit dans document_field, restreinte aux champs
portant au moins une field_proposal — la seule preuve qu'un humain a regarde le
champ, l'IHM envoyant une proposition aussi bien pour confirmer que pour
corriger. Copier 120 000 valeurs (dont des IBAN et des NIR) hors de leur
contexte rendrait le droit a l'effacement inapplicable ; referencer laisse la
suppression d'un document faire son travail.

Le perimetre est porte par ``document_ids`` plutot que par une table de
liaison : 200 entiers dans un ARRAY, fige au verrouillage, et une table de
moins a scoper, migrer et tester. Si un document du perimetre est supprime, le
worker le constate au lancement et le signale — le tableau reste la reference
de ce qui ETAIT attendu.

Deux passages ne sont comparables que si la recette n'a pas bouge entre eux :
d'ou le statut LOCKED, prerequis de toute execution.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from adam_core.db.base import Base
from adam_core.db.scoping import (
    OrganisationScoped,
    ProjectScoped,
    member_dataset_ids,
    org_dataset_ids,
)
from adam_core.enums.status import TestRecipeStatus

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class TestRecipe(OrganisationScoped, ProjectScoped, Base):
    __tablename__ = "test_recipe"

    # pytest collecte les classes prefixees Test* importees dans un module de
    # test ; ce marqueur l'en dissuade sans renommer la table du cahier des
    # charges.
    __test__ = False

    __table_args__ = (
        UniqueConstraint("dataset_id", "name", name="uq_test_recipe_dataset_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("dataset.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    #: Perimetre fige au verrouillage : ids des documents evalues.
    document_ids: Mapped[List[int]] = mapped_column(ARRAY(Integer), nullable=False)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=TestRecipeStatus.DRAFT.value,
        comment="Cycle de vie : DRAFT, LOCKED, ARCHIVED",
    )
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @classmethod
    def __organisation_filter__(cls, organisation_id: int) -> "ColumnElement[bool]":
        # test_recipe -> dataset -> project -> organisation
        return cls.dataset_id.in_(org_dataset_ids(organisation_id))

    @classmethod
    def __project_filter__(cls, matricule: str) -> "ColumnElement[bool]":
        return cls.dataset_id.in_(member_dataset_ids(matricule))

    def __repr__(self) -> str:
        return (
            f"<TestRecipe id={self.id} name={self.name!r} status={self.status!r} "
            f"documents={len(self.document_ids) if self.document_ids else 0}>"
        )
