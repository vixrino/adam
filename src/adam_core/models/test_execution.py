"""Table TEST_EXECUTION : un passage d'une recette contre le moteur OCR.

C'est la seule entite du domaine qui n'est reconstituable d'aucune autre :
quand le passage a eu lieu, contre quel moteur, et ce qu'il a constate en
totaux. ``ocr_provider`` et ``ocr_model_id`` sont copies au lancement plutot
que lus sur le dataset, dont la configuration change apres coup. ``started_at``
est le vrai axe temporel : Mistral s'ameliore derriere un model_id stable, un
identifiant constant ne date rien.

La comparaison se fait EN MEMOIRE dans le worker : le connecteur est appele,
sa sortie est comparee a la verite, et seuls les ecarts sont ecrits. Aucune
table de production (ocr_result, document_field) n'est touchee — un benchmark
ne doit jamais modifier la donnee qu'il mesure.

``confidence_histogram`` porte la distribution de la confiance OCR chez les
champs corrects ET chez les faux (JSONB, ~100 tranches par type de valeur).
C'est la seule information definitivement perdue si elle n'est pas ecrite au
fil du run, les champs corrects ne produisant aucune ligne : elle repond a
« a partir de quel seuil de confiance l'auto-validation est-elle sure », la
question qui chiffre l'economie de relecture humaine.

``fields_human_verified`` compte les champs du perimetre portant au moins une
field_proposal. C'est le denominateur honnete du rapport : les champs jamais
regardes par un humain ont resolved_value == ocr_value par construction
(cf. services/consensus.py), et les compter mesurerait le moteur contre
lui-meme.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from adam_core.db.base import Base
from adam_core.db.scoping import (
    OrganisationScoped,
    ProjectScoped,
    member_test_recipe_ids,
    org_test_recipe_ids,
)
from adam_core.enums.status import TestExecutionStatus

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class TestExecution(OrganisationScoped, ProjectScoped, Base):
    __tablename__ = "test_execution"

    # pytest collecte les classes prefixees Test* importees dans un module de
    # test ; ce marqueur l'en dissuade.
    __test__ = False

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipe_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("test_recipe.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=TestExecutionStatus.PENDING.value,
        index=True,
        comment="PENDING, RUNNING, COMPLETED, FAILED",
    )
    #: Copies au lancement : la configuration du dataset peut changer apres.
    ocr_provider: Mapped[str] = mapped_column(String, nullable=False)
    ocr_model_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # -- Totaux du passage ---------------------------------------------------
    documents_compared: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fields_compared: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Sous-ensemble de fields_compared porte par au moins une field_proposal.
    fields_human_verified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    diff_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Champs lus par le moteur hors du schema attendu. Comptes ici et non en
    #: lignes : un champ hors schema n'a pas de document_field a referencer.
    unexpected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ocr_calls_made: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Distribution de la confiance OCR, corrects inclus, par type de valeur :
    #: {"TEXT": {"0.95": [corrects, ecarts], ...}, ...}. Irrecuperable apres
    #: coup, les champs corrects n'ayant pas de ligne.
    confidence_histogram: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    created_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("user.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    @classmethod
    def __organisation_filter__(cls, organisation_id: int) -> "ColumnElement[bool]":
        # test_execution -> test_recipe -> dataset -> project -> organisation
        return cls.recipe_id.in_(org_test_recipe_ids(organisation_id))

    @classmethod
    def __project_filter__(cls, matricule: str) -> "ColumnElement[bool]":
        return cls.recipe_id.in_(member_test_recipe_ids(matricule))

    def __repr__(self) -> str:
        return (
            f"<TestExecution id={self.id} recipe_id={self.recipe_id} "
            f"status={self.status!r} provider={self.ocr_provider!r}>"
        )
