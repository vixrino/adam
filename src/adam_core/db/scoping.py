"""Filtrage multi-tenant par organisation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional, cast

from sqlalchemy import event, literal, or_, select
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from adam_core.enums.roles import ProjectRole

if TYPE_CHECKING:
    from sqlalchemy.orm.interfaces import ORMOption
    from sqlalchemy.sql.elements import ColumnElement
    from sqlalchemy.sql.selectable import Select

SESSION_ORG_KEY = "organisation_id"

SESSION_MATRICULE_KEY = "matricule"

SKIP_ORG_FILTER = "skip_organisation_filter"


class OrganisationScoped:
    """Marqueur : les lignes de cette table sont isolees par organisation.."""

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
    """Marqueur : les lignes de cette table sont en plus isolees par projet."""

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
    """Vrai si ce matricule porte BUSINESS_ADMIN sur au moins un projet."""
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
    """Projets visibles par ce matricule au titre du second etage."""
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
    """Retourne toutes les classes mappees heritant de OrganisationScoped."""
    global _scoped_models_cache
    if _scoped_models_cache is None:
        from adam_core.db.base import Base
        import adam_core.models  # noqa: F401 - garantit que tous les modeles sont mappes

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
        from adam_core.db.base import Base
        import adam_core.models  # noqa: F401 - garantit que tous les modeles sont mappes

        _project_scoped_models_cache = [
            mapper.class_
            for mapper in Base.registry.mappers
            if issubclass(mapper.class_, ProjectScoped)
        ]
    return _project_scoped_models_cache


def _apply_organisation_filter(execute_state: ORMExecuteState) -> None:
    """Listener do_orm_execute : injecte les filtres organisation et projet."""
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
