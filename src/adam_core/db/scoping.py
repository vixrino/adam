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

Table volontairement NON scopee :
    - file : contenu physique deduplique par sha256, partage entre plusieurs
      documents (potentiellement de plusieurs organisations). Il n'existe
      aucune FK de file vers organisation. L'acces est medie par document,
      lui-meme scope : lister/lire un file passe par un document autorise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional, cast

from sqlalchemy import event, select
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.sql.selectable import Select

# Cle posee en session.info ; sa presence (non None) active le filtre.
SESSION_ORG_KEY = "organisation_id"

# Option d'execution permettant a un appelant de confiance de desactiver
# explicitement le filtre sur une requete precise (ex. taches d'administration).
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


# ---------------------------------------------------------------------------
# Sous-requetes composables pour les tables sans organisation_id direct.
# Chaque helper renvoie un SELECT des ids appartenant a l'organisation, en
# remontant la chaine de FK. Les imports sont locaux pour eviter les cycles
# (les modeles importent ce module pour le mixin).
# ---------------------------------------------------------------------------


def org_project_ids(organisation_id: int) -> "Select[tuple[int]]":
    from adam_core.models.project import Project

    return select(Project.id).where(Project.organisation_id == organisation_id)


def org_dataset_ids(organisation_id: int) -> "Select[tuple[int]]":
    from adam_core.models.dataset import Dataset

    return select(Dataset.id).where(Dataset.project_id.in_(org_project_ids(organisation_id)))


def org_schema_ids(organisation_id: int) -> "Select[tuple[int]]":
    from adam_core.models.doc_schema import DocSchema

    return select(DocSchema.id).where(DocSchema.project_id.in_(org_project_ids(organisation_id)))


def org_document_ids(organisation_id: int) -> "Select[tuple[int]]":
    from adam_core.models.document import Document

    return select(Document.id).where(Document.dataset_id.in_(org_dataset_ids(organisation_id)))


def org_job_ids(organisation_id: int) -> "Select[tuple[int]]":
    from adam_core.models.job import Job

    return select(Job.id).where(Job.dataset_id.in_(org_dataset_ids(organisation_id)))


def org_user_ids(organisation_id: int) -> "Select[tuple[int]]":
    from adam_core.models.user import User

    return select(User.id).where(User.organisation_id == organisation_id)


_scoped_models_cache: Optional[list[type[OrganisationScoped]]] = None


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


def _apply_organisation_filter(execute_state: ORMExecuteState) -> None:
    """Listener do_orm_execute : injecte le filtre organisation.

    Ne s'applique qu'aux SELECT ORM de premier niveau. Les chargements de
    colonnes (deferred/refresh) et de relations (lazy/eager secondaires) sont
    ignores, conformement a la recette SQLAlchemy : l'entite parente etant
    deja filtree, ses objets lies lui appartiennent.
    """
    if (
        not execute_state.is_select
        or execute_state.is_column_load
        or execute_state.is_relationship_load
        or execute_state.execution_options.get(SKIP_ORG_FILTER, False)
    ):
        return

    organisation_id = execute_state.session.info.get(SESSION_ORG_KEY)
    if organisation_id is None:
        # Aucun contexte organisation (ex. service machine, worker) : pas de
        # filtre. L'isolation ne s'applique qu'aux appelants "utilisateur".
        return

    execute_state.statement = execute_state.statement.options(
        *(
            with_loader_criteria(
                model,
                model.__organisation_filter__(organisation_id),
                include_aliases=True,
            )
            for model in _iter_scoped_models()
        )
    )


def register_organisation_filter() -> None:
    """Enregistre le listener global (idempotent)."""
    if not event.contains(Session, "do_orm_execute", _apply_organisation_filter):
        event.listen(Session, "do_orm_execute", _apply_organisation_filter)


# Enregistrement a l'import du module.
register_organisation_filter()
