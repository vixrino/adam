"""Table EVALUATION_REPORT : l'agregat par champ d'une execution.

Une ligne par field_spec et par execution : combien de champs compares, combien
d'ecarts. 600 lignes par passage, conservees indefiniment — c'est l'historique
qui repond a « ce champ s'ameliore-t-il depuis six mois », et qui survivra a
une purge future des ecarts detailles.

``field_key`` est denormalise a cote de field_spec_id : quand le schema sera
re-versionne, les ids changeront et l'historique par champ se couperait net.
Le libelle assure la continuite des courbes a travers les versions, pour une
colonne.

Les totaux globaux du passage vivent sur test_execution, pas ici : une table de
rapport a une ligne par execution serait une jointure et un risque de
desynchronisation pour rien.

Pas de reference au document, volontairement : la suppression d'un document
(droit a l'effacement) emporte ses ecarts detailles mais laisse intactes les
mesures agregees deja publiees.
"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from adam_core.db.base import Base
from adam_core.db.scoping import (
    OrganisationScoped,
    ProjectScoped,
    member_test_execution_ids,
    org_test_execution_ids,
)

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class EvaluationReport(OrganisationScoped, ProjectScoped, Base):
    __tablename__ = "evaluation_report"

    __table_args__ = (
        # Idempotence : l'agregation d'une reprise ecrase ou ignore, ne double pas.
        UniqueConstraint(
            "execution_id",
            "field_spec_id",
            name="uq_evaluation_report_execution_field_spec",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    execution_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("test_execution.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_spec_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("field_spec.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: Libelle fige : la continuite de l'historique quand les ids de schema
    #: changent.
    field_key: Mapped[str] = mapped_column(String, nullable=False)
    compared: Mapped[int] = mapped_column(Integer, nullable=False)
    diff_count: Mapped[int] = mapped_column(Integer, nullable=False)

    @classmethod
    def __organisation_filter__(cls, organisation_id: int) -> "ColumnElement[bool]":
        # evaluation_report -> test_execution -> test_recipe -> dataset -> project
        return cls.execution_id.in_(org_test_execution_ids(organisation_id))

    @classmethod
    def __project_filter__(cls, matricule: str) -> "ColumnElement[bool]":
        return cls.execution_id.in_(member_test_execution_ids(matricule))

    def __repr__(self) -> str:
        return (
            f"<EvaluationReport id={self.id} execution_id={self.execution_id} "
            f"field_key={self.field_key!r} compared={self.compared} "
            f"diff_count={self.diff_count}>"
        )
