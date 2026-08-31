"""Filtrage multi-tenant par organisation.

Fondations pour l'isolation des donnees par organisation, en attendant
l'integration FBI reelle. Le point d'entree reste le caller resolu
(cf. adam_api.dependencies.auth.get_caller) : seule la facon de determiner
l'organisation_id changera quand le FBI sera branche, pas ce mecanisme.

Approche (validee avec Daniel) : un mixin marqueur ``OrganisationScoped``
pose sur chaque table a isoler, plus un listener global ``do_orm_execute``
qui injecte, via ``with_loader_criteria``, un filtre par organisation sur
toutes les tables scopees. Aucune modification route par route n'est
necessaire : le filtre suit l'``organisation_id`` pose en ``session.info``.

Audit de la chaine de FK vers organisation
------------------------------------------
Tables portant ``organisation_id`` directement :
    - organisation (via son propre ``id``)
    - user
    - project

Tables sans ``organisation_id`` direct : le filtre remonte la chaine de FK
par sous-requete (branche "filtre par jointure" de l'audit). Le filtrage du
seul parent ne suffit PAS : les routes interrogent les enfants directement
(``select(Document).where(...)``), une requete qui ne touche jamais Project,
donc un critere pose uniquement sur Project ne se declencherait pas.

    doc_schema      -> project
    dataset         -> project
    field_spec      -> doc_schema -> project
    document        -> dataset -> project
    job             -> dataset -> project
    ocr_result      -> dataset -> project
    document_field  -> document -> dataset -> project
    field_proposal  -> job -> dataset -> project
    user_project    -> user (direct)
    test_recipe        -> dataset -> project
    test_execution     -> test_recipe -> dataset -> project
    comparison_result  -> test_execution -> test_recipe -> dataset -> project
    evaluation_report  -> test_execution -> test_recipe -> dataset -> project

Table volontairement NON scopee :
    - file : contenu physique deduplique par sha256, partage entre plusieurs
      documents (potentiellement de plusieurs organisations). Il n'existe
      aucune FK de file vers organisation. L'acces est medie par document,
      lui-meme scope : lister/lire un file passe par un document autorise.

Second etage : filtrage par projet
-----------------------------------
Le filtre organisation seul laisse un utilisateur voir tous les projets de son
organisation, et donc tous leurs documents, qu'il y soit inscrit ou non. Le
mixin ``ProjectScoped`` ajoute un etage : les tables qui derivent d'un projet
sont en plus restreintes aux adhesions de l'appelant, lues dans user_project.

    project         (via son propre id)
    dataset         -> project
    doc_schema      -> project
    user_project    -> project
    document        -> dataset -> project
    job             -> dataset -> project
    ocr_result      -> dataset -> project
    field_spec      -> doc_schema -> project
    document_field  -> document -> dataset -> project
    field_proposal  -> job -> dataset -> project
    test_recipe        -> dataset -> project
    test_execution     -> test_recipe -> dataset -> project
    comparison_result  -> test_execution -> test_recipe -> dataset -> project
    evaluation_report  -> test_execution -> test_recipe -> dataset -> project

Tables volontairement hors du second etage :
    - organisation : l'appelant doit pouvoir lire la sienne, qui n'appartient
      a aucun projet.
    - user : le referentiel des utilisateurs de l'organisation reste lisible,
      notamment pour affecter quelqu'un a un projet. Le restreindre aux seuls
      co-equipiers casserait cette affectation.

Qui est reellement restreint
-----------------------------
Le tableau de controle d'acces reserve la restriction a l'Operateur Metier :

    Lecture transverse | Operateur : Non | Admin Metier : Oui (projets)
                       | Superviseur NOTA : Oui | Admin NOTA : Oui

Les deux roles NOTA sont deja hors filtre, leur session n'etant pas scopee.
Restait l'Administrateur Metier, a qui la lecture transverse est accordee et que
le second etage ne doit donc pas enfermer dans ses adhesions. La mention
"(projets)" la borne au perimetre des projets, la ou les roles NOTA l'ont sans
reserve ; le filtre organisation restant actif par-dessus, sa portee effective
est l'ensemble des projets de son organisation.

Cette distinction est portee par ``member_project_ids``, en un seul endroit :
toutes les chaines member_* y transitent. Le ProjectRole etant porte par
l'adhesion, un compte BUSINESS_ADMIN sur au moins un projet ouvre la lecture
transverse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional, cast

from sqlalchemy import event, literal, or_, select
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from adam_core.enums.roles import ProjectRole

if TYPE_CHECKING:
    from sqlalchemy.orm.interfaces import ORMOption
    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.sql.selectable import Select

# Cle posee en session.info ; sa presence (non None) active le filtre.
SESSION_ORG_KEY = "organisation_id"

# Cle posee en session.info pour le second etage de filtrage : le matricule de
# l'appelant restreint les tables ProjectScoped a ses seules adhesions. Absente
# (services machine, roles plateforme), seul le filtre organisation s'applique.
SESSION_MATRICULE_KEY = "matricule"

# Option d'execution permettant a un appelant de confiance de desactiver
# explicitement le filtre sur une requete precise (ex. taches d'administration).
# Desactive les deux etages : organisation ET projet.
SKIP_ORG_FILTER = "skip_organisation_filter"


class OrganisationScoped:
    """Marqueur : les lignes de cette table sont isolees par organisation.

    Par defaut, le filtre suppose une colonne ``organisation_id`` sur la
    table (cas des tables portant la FK directement). Les tables sans
    ``organisation_id`` direct DOIVENT redefinir ``__organisation_filter__``
    pour remonter la chaine de FK ; sinon une ``NotImplementedError`` est
    levee, garantissant qu'aucune table scopee ne reste sans critere (fail
    closed).
    """

    @classmethod
    def __organisation_filter__(cls, organisation_id: int) -> "ColumnElement[bool]":
        column = getattr(cls, "organisation_id", None)
        if column is None:
            raise NotImplementedError(
                f"{cls.__name__} herite de OrganisationScoped mais n'a pas de "
                f"colonne organisation_id : redefinir __organisation_filter__ "
                f"pour remonter la chaine de FK."
            )
        # getattr sur une colonne dynamique -> Any ; on retype explicitement.
        return cast("ColumnElement[bool]", column == organisation_id)


class ProjectScoped:
    """Marqueur : les lignes de cette table sont en plus isolees par projet.

    Second etage, orthogonal au premier : une table peut etre scopee par
    organisation seule (``organisation``, ``user``) ou par les deux. Quand les
    deux s'appliquent, les criteres se cumulent en AND, le filtre projet ne
    pouvant qu'ajouter une restriction.

    Par defaut, le filtre suppose une colonne ``project_id`` sur la table. Les
    tables sans ``project_id`` direct DOIVENT redefinir ``__project_filter__``
    pour remonter la chaine de FK ; sinon une ``NotImplementedError`` est levee,
    par symetrie avec OrganisationScoped et pour la meme raison (fail closed).
    """

    @classmethod
    def __project_filter__(cls, matricule: str) -> "ColumnElement[bool]":
        column = getattr(cls, "project_id", None)
        if column is None:
            raise NotImplementedError(
                f"{cls.__name__} herite de ProjectScoped mais n'a pas de colonne "
                f"project_id : redefinir __project_filter__ pour remonter la "
                f"chaine de FK."
            )
        return cast("ColumnElement[bool]", column.in_(member_project_ids(matricule)))


# ---------------------------------------------------------------------------
# Sous-requetes d'adhesion, pour le filtre projet.
#
# Comme les helpers org_* ci-dessous, elles sont construites sur les Table Core
# (``__table__``) et non sur les classes ORM. Le listener injecte ses criteres
# via with_loader_criteria(include_aliases=True), qui vise les entites ORM
# presentes dans la requete : bati sur l'ORM, member_project_ids ferait
# reapparaitre le critere de UserProject a l'interieur de sa propre definition.
# Le niveau Core est inatteignable par with_loader_criteria, ce qui coupe court.
# ---------------------------------------------------------------------------


def _adhesion_project_ids(matricule: str) -> "Select[tuple[int]]":
    """Projets ou l'utilisateur de ce matricule est inscrit, sans exception."""
    from adam_core.models.user import User
    from adam_core.models.user_project import UserProject

    user_project = UserProject.__table__
    user = User.__table__
    return (
        select(user_project.c.project_id)
        .join(user, user.c.id == user_project.c.user_id)
        .where(user.c.matricule == matricule)
    )


def _has_transverse_project_read(matricule: str) -> "ColumnElement[bool]":
    """Vrai si ce matricule porte BUSINESS_ADMIN sur au moins un projet.

    Le tableau de controle d'acces accorde la lecture transverse a
    l'Administrateur Metier, avec la mention "(projets)" qui la borne au
    perimetre des projets la ou le Superviseur et l'Administrateur NOTA l'ont
    sans reserve. Le filtre organisation continuant de s'appliquer par-dessus,
    la portee effective est : tous les projets de son organisation.

    Le ProjectRole etant porte par l'adhesion et non par l'utilisateur, un meme
    compte peut etre OPERATOR ici et BUSINESS_ADMIN la. La lecture transverse
    est une propriete du role, pas de l'adhesion : la porter sur un seul projet
    suffit a l'ouvrir. Restreindre l'Administrateur Metier aux projets ou il est
    inscrit reviendrait a lui refuser la lecture transverse que le tableau lui
    accorde.
    """
    from adam_core.models.user import User
    from adam_core.models.user_project import UserProject

    user_project = UserProject.__table__
    user = User.__table__
    return (
        select(literal(1))
        .select_from(user_project.join(user, user.c.id == user_project.c.user_id))
        .where(
            user.c.matricule == matricule,
            user_project.c.role == ProjectRole.BUSINESS_ADMIN.value,
        )
        .exists()
    )


def member_project_ids(matricule: str) -> "Select[tuple[int]]":
    """Projets visibles par ce matricule au titre du second etage.

    Ses adhesions, ou l'integralite des projets s'il porte BUSINESS_ADMIN
    quelque part. Toutes les autres chaines member_* transitent par ici, la
    distinction Operateur / Administrateur Metier n'a donc a etre exprimee
    qu'une fois.
    """
    from adam_core.models.project import Project

    project = Project.__table__
    return select(project.c.id).where(
        or_(
            project.c.id.in_(_adhesion_project_ids(matricule)),
            _has_transverse_project_read(matricule),
        )
    )


def member_dataset_ids(matricule: str) -> "Select[tuple[int]]":
    from adam_core.models.dataset import Dataset

    dataset = Dataset.__table__
    return select(dataset.c.id).where(dataset.c.project_id.in_(member_project_ids(matricule)))


def member_schema_ids(matricule: str) -> "Select[tuple[int]]":
    from adam_core.models.doc_schema import DocSchema

    doc_schema = DocSchema.__table__
    return select(doc_schema.c.id).where(doc_schema.c.project_id.in_(member_project_ids(matricule)))


def member_test_recipe_ids(matricule: str) -> "Select[tuple[int]]":
    from adam_core.models.test_recipe import TestRecipe

    test_recipe = TestRecipe.__table__
    return select(test_recipe.c.id).where(
        test_recipe.c.dataset_id.in_(member_dataset_ids(matricule))
    )


def member_test_execution_ids(matricule: str) -> "Select[tuple[int]]":
    from adam_core.models.test_execution import TestExecution

    test_execution = TestExecution.__table__
    return select(test_execution.c.id).where(
        test_execution.c.recipe_id.in_(member_test_recipe_ids(matricule))
    )


def member_document_ids(matricule: str) -> "Select[tuple[int]]":
    from adam_core.models.document import Document

    document = Document.__table__
    return select(document.c.id).where(document.c.dataset_id.in_(member_dataset_ids(matricule)))


def member_job_ids(matricule: str) -> "Select[tuple[int]]":
    from adam_core.models.job import Job

    job = Job.__table__
    return select(job.c.id).where(job.c.dataset_id.in_(member_dataset_ids(matricule)))


# ---------------------------------------------------------------------------
# Sous-requetes composables pour les tables sans organisation_id direct.
# Chaque helper renvoie un SELECT des ids appartenant a l'organisation, en
# remontant la chaine de FK. Les imports sont locaux pour eviter les cycles
# (les modeles importent ce module pour le mixin).
#
# Comme les helpers member_* ci-dessus, elles sont batties sur les Table Core :
# construites sur les classes ORM, with_loader_criteria y re-injectait ses
# criteres, produisant un SQL ou chaque condition apparaissait en double a
# chaque niveau d'imbrication. Le resultat restait juste, la requete inutilement
# lourde.
# ---------------------------------------------------------------------------


def org_project_ids(organisation_id: int) -> "Select[tuple[int]]":
    from adam_core.models.project import Project

    project = Project.__table__
    return select(project.c.id).where(project.c.organisation_id == organisation_id)


def org_dataset_ids(organisation_id: int) -> "Select[tuple[int]]":
    from adam_core.models.dataset import Dataset

    dataset = Dataset.__table__
    return select(dataset.c.id).where(dataset.c.project_id.in_(org_project_ids(organisation_id)))


def org_test_recipe_ids(organisation_id: int) -> "Select[tuple[int]]":
    from adam_core.models.test_recipe import TestRecipe

    test_recipe = TestRecipe.__table__
    return select(test_recipe.c.id).where(
        test_recipe.c.dataset_id.in_(org_dataset_ids(organisation_id))
    )


def org_test_execution_ids(organisation_id: int) -> "Select[tuple[int]]":
    from adam_core.models.test_execution import TestExecution

    test_execution = TestExecution.__table__
    return select(test_execution.c.id).where(
        test_execution.c.recipe_id.in_(org_test_recipe_ids(organisation_id))
    )


def org_schema_ids(organisation_id: int) -> "Select[tuple[int]]":
    from adam_core.models.doc_schema import DocSchema

    doc_schema = DocSchema.__table__
    return select(doc_schema.c.id).where(
        doc_schema.c.project_id.in_(org_project_ids(organisation_id))
    )


def org_document_ids(organisation_id: int) -> "Select[tuple[int]]":
    from adam_core.models.document import Document

    document = Document.__table__
    return select(document.c.id).where(document.c.dataset_id.in_(org_dataset_ids(organisation_id)))


def org_job_ids(organisation_id: int) -> "Select[tuple[int]]":
    from adam_core.models.job import Job

    job = Job.__table__
    return select(job.c.id).where(job.c.dataset_id.in_(org_dataset_ids(organisation_id)))


def org_user_ids(organisation_id: int) -> "Select[tuple[int]]":
    from adam_core.models.user import User

    user = User.__table__
    return select(user.c.id).where(user.c.organisation_id == organisation_id)


_scoped_models_cache: Optional[list[type[OrganisationScoped]]] = None
_project_scoped_models_cache: Optional[list[type[ProjectScoped]]] = None


def _iter_scoped_models() -> Iterable[type[OrganisationScoped]]:
    """Retourne toutes les classes mappees heritant de OrganisationScoped.

    Le resultat est mis en cache apres la premiere resolution : la liste des
    modeles est fixe une fois les mappers configures.
    """
    global _scoped_models_cache
    if _scoped_models_cache is None:
        import adam_core.models  # noqa: F401 - garantit que tous les modeles sont mappes
        from adam_core.db.base import Base

        _scoped_models_cache = [
            mapper.class_
            for mapper in Base.registry.mappers
            if issubclass(mapper.class_, OrganisationScoped)
        ]
    return _scoped_models_cache


def _iter_project_scoped_models() -> Iterable[type[ProjectScoped]]:
    """Retourne toutes les classes mappees heritant de ProjectScoped."""
    global _project_scoped_models_cache
    if _project_scoped_models_cache is None:
        import adam_core.models  # noqa: F401 - garantit que tous les modeles sont mappes
        from adam_core.db.base import Base

        _project_scoped_models_cache = [
            mapper.class_
            for mapper in Base.registry.mappers
            if issubclass(mapper.class_, ProjectScoped)
        ]
    return _project_scoped_models_cache


def _apply_organisation_filter(execute_state: ORMExecuteState) -> None:
    """Listener do_orm_execute : injecte les filtres organisation et projet.

    Ne s'applique qu'aux SELECT ORM de premier niveau. Les chargements de
    colonnes (deferred/refresh) et de relations (lazy/eager secondaires) sont
    ignores, conformement a la recette SQLAlchemy : l'entite parente etant
    deja filtree, ses objets lies lui appartiennent.

    Les deux etages sont independants et cumulatifs. Le second ne se declenche
    que si un matricule est pose en session, ce que ``get_db`` ne fait que pour
    un utilisateur sans role de plateforme : les roles NOTA et les services
    machine n'ouvrent aucun des deux.
    """
    if (
        not execute_state.is_select
        or execute_state.is_column_load
        or execute_state.is_relationship_load
        or execute_state.execution_options.get(SKIP_ORG_FILTER, False)
    ):
        return

    options: list["ORMOption"] = []

    organisation_id = execute_state.session.info.get(SESSION_ORG_KEY)
    if organisation_id is not None:
        # Aucun contexte organisation (ex. service machine, worker) : pas de
        # filtre. L'isolation ne s'applique qu'aux appelants "utilisateur".
        options.extend(
            with_loader_criteria(
                model,
                model.__organisation_filter__(organisation_id),
                include_aliases=True,
            )
            for model in _iter_scoped_models()
        )

    matricule = execute_state.session.info.get(SESSION_MATRICULE_KEY)
    if matricule is not None:
        options.extend(
            with_loader_criteria(
                model,
                model.__project_filter__(matricule),
                include_aliases=True,
            )
            for model in _iter_project_scoped_models()
        )

    if options:
        execute_state.statement = execute_state.statement.options(*options)


def register_organisation_filter() -> None:
    """Enregistre le listener global (idempotent)."""
    if not event.contains(Session, "do_orm_execute", _apply_organisation_filter):
        event.listen(Session, "do_orm_execute", _apply_organisation_filter)


# Enregistrement a l'import du module.
register_organisation_filter()
