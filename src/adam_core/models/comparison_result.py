"""Table COMPARISON_RESULT : un ecart constate entre le moteur et la verite.

Seuls les ecarts sont ecrits, jamais les champs corrects : sur 600 champs par
document, la liste des justes est du bruit, et les totaux vivent sur
l'execution. Un champ correct se deduit — present dans le perimetre, absent
d'ici.

Confidentialite : la valeur selon la sensibilite du champ
----------------------------------------------------------
Les documents portent des IBAN et des NIR, concentres sur une minorite de
champs. La regle, appliquee par le worker et portee par field_spec.is_sensitive :

    champ non sensible   expected_value et observed_value en clair — c'est ce
                         qui rend le debogage reel possible (« qu'a lu le
                         moteur ? »)
    champ sensible       les deux valeurs a NULL ; observed_hmac (HMAC a cle
                         hors base de la valeur lue) et edit_distance portent
                         le diagnostic : la recurrence d'une meme erreur et son
                         ampleur, sans rien reveler

``created_at`` est non nullable des la creation : l'ajouter plus tard datera
toutes les lignes historiques du jour de l'ALTER, une perte irreversible. Et
``id`` est un BigInteger : la table est la seule du domaine a croitre en
millions de lignes par an, et le passage tardif int4 -> int8 est une reecriture
complete sous verrou exclusif.

La cle etrangere vers document_field est en CASCADE, volontairement : la
suppression d'un document emporte ses ecarts, le droit a l'effacement n'a pas
besoin d'une procedure dediee. L'historique agrege survit dans
evaluation_report, qui ne reference pas le document.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from adam_core.db.base import Base
from adam_core.db.scoping import (
    OrganisationScoped,
    ProjectScoped,
    member_test_execution_ids,
    org_test_execution_ids,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class ComparisonResult(OrganisationScoped, ProjectScoped, Base):
    __tablename__ = "comparison_result"

    __table_args__ = (
        # Idempotence de la reprise : un worker qui rejoue un document apres un
        # plantage retombe sur la contrainte au lieu de doubler les ecarts.
        # document_field_id porte deja le document et le group_id : pas de
        # colonne group_id ici, donc pas de piege NULL <> NULL.
        UniqueConstraint(
            "execution_id",
            "document_field_id",
            name="uq_comparison_result_execution_field",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    execution_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("test_execution.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_field_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("document_field.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    verdict: Mapped[str] = mapped_column(
        String, nullable=False, comment="MISSING ou WRONG, cf. ComparisonVerdict"
    )
    diff_kind: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, comment="Categorie d'un WRONG, cf. ComparisonDiffKind"
    )
    #: Confiance annoncee par le moteur sur ce champ, pour croiser erreur et
    #: certitude — un moteur sur de ses erreurs est plus dangereux qu'un moteur
    #: hesitant.
    ocr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    #: Renseignees uniquement si field_spec.is_sensitive est faux.
    expected_value: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    observed_value: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    #: Renseignees uniquement si field_spec.is_sensitive est vrai.
    observed_hmac: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    edit_distance: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    @classmethod
    def __organisation_filter__(cls, organisation_id: int) -> "ColumnElement[bool]":
        # comparison_result -> test_execution -> test_recipe -> dataset -> project
        return cls.execution_id.in_(org_test_execution_ids(organisation_id))

    @classmethod
    def __project_filter__(cls, matricule: str) -> "ColumnElement[bool]":
        return cls.execution_id.in_(member_test_execution_ids(matricule))

    def __repr__(self) -> str:
        # Jamais les valeurs : expected/observed peuvent porter un IBAN.
        return (
            f"<ComparisonResult id={self.id} execution_id={self.execution_id} "
            f"document_field_id={self.document_field_id} verdict={self.verdict!r} "
            f"diff_kind={self.diff_kind!r}>"
        )
