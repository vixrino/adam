"""Tests du filtrage multi-tenant par organisation (adam_core.db.scoping).

Couvre les criteres d'acceptation du ticket :
    CA-1 : get_async_session pose organisation_id en session.info ; get_db le
           derive du caller resolu (UserCaller -> org, ServiceCaller -> None).
    CA-2 : toute requete sur une table a organisation_id direct est filtree.
    CA-3 : les tables sans organisation_id direct sont filtrees par jointure.
    CA-4 : une ressource hors organisation est exclue (-> 404 cote route).
    CA-5 : un caller de test avec organisation_id fixe (fixture partagee).
"""

from types import SimpleNamespace
from typing import Any, Optional

import pytest
from sqlalchemy import select
from sqlalchemy.orm import with_loader_criteria

import adam_core.models  # noqa: F401 - force le mapping de tous les modeles
from adam_core.db.scoping import (
    SESSION_ORG_KEY,
    SKIP_ORG_FILTER,
    OrganisationScoped,
    _apply_organisation_filter,
    _iter_scoped_models,
)
from adam_core.models import (
    Dataset,
    DocSchema,
    Document,
    DocumentField,
    FieldProposal,
    FieldSpec,
    File,
    Job,
    OcrResult,
    Organisation,
    Project,
    User,
    UserProject,
)

# CA-5 : caller de test avec organisation fixe, reutilisable par les fixtures.
TEST_ORG_ID = 42


@pytest.fixture
def test_caller() -> Any:
    from adam_api.dependencies.auth import UserCaller

    return UserCaller(matricule="MATTEST", organisation_id=TEST_ORG_ID)


def _compile(stmt: Any) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def _fake_execute_state(
    statement: Any,
    *,
    organisation_id: Optional[int],
    is_select: bool = True,
    is_column_load: bool = False,
    is_relationship_load: bool = False,
    execution_options: Optional[dict] = None,
) -> SimpleNamespace:
    """Imite un ORMExecuteState pour tester le listener sans base reelle."""
    info: dict = {}
    if organisation_id is not None:
        info[SESSION_ORG_KEY] = organisation_id
    return SimpleNamespace(
        statement=statement,
        is_select=is_select,
        is_column_load=is_column_load,
        is_relationship_load=is_relationship_load,
        execution_options=execution_options or {},
        session=SimpleNamespace(info=info),
    )


# ---------------------------------------------------------------------------
# Recensement des tables scopees (CA-2 / CA-3)
# ---------------------------------------------------------------------------


class TestScopedRegistry:
    def test_direct_org_tables_are_scoped(self) -> None:
        scoped = set(_iter_scoped_models())
        assert {Organisation, User, Project} <= scoped

    def test_indirect_tables_are_scoped(self) -> None:
        scoped = set(_iter_scoped_models())
        assert {
            Dataset,
            DocSchema,
            Document,
            DocumentField,
            FieldProposal,
            FieldSpec,
            Job,
            OcrResult,
            UserProject,
        } <= scoped

    def test_file_is_not_scoped(self) -> None:
        # file : contenu deduplique partage inter-organisations, hors scope.
        assert not issubclass(File, OrganisationScoped)
        assert File not in set(_iter_scoped_models())

    def test_every_scoped_model_has_working_filter(self) -> None:
        # CA-3 : aucune table scopee ne reste sans critere coherent.
        for model in _iter_scoped_models():
            sql = _compile(select(model).options(
                with_loader_criteria(model, model.__organisation_filter__(TEST_ORG_ID))
            ))
            assert "organisation_id = 42" in sql or "organisation.id = 42" in sql


# ---------------------------------------------------------------------------
# Criteres de filtre par table (CA-2 direct, CA-3 par jointure)
# ---------------------------------------------------------------------------


class TestOrganisationFilters:
    def test_project_direct_column(self) -> None:
        sql = _compile(select(Project).where(Project.__organisation_filter__(TEST_ORG_ID)))
        assert "project.organisation_id = 42" in sql

    def test_user_direct_column(self) -> None:
        sql = _compile(select(User).where(User.__organisation_filter__(TEST_ORG_ID)))
        assert '"user".organisation_id = 42' in sql

    def test_organisation_filters_on_own_id(self) -> None:
        sql = _compile(select(Organisation).where(Organisation.__organisation_filter__(TEST_ORG_ID)))
        assert "organisation.id = 42" in sql

    def test_dataset_via_project(self) -> None:
        sql = _compile(select(Dataset).where(Dataset.__organisation_filter__(TEST_ORG_ID)))
        assert "dataset.project_id IN" in sql
        assert "project.organisation_id = 42" in sql

    def test_document_via_dataset_project(self) -> None:
        sql = _compile(select(Document).where(Document.__organisation_filter__(TEST_ORG_ID)))
        assert "document.dataset_id IN" in sql
        assert "project.organisation_id = 42" in sql

    def test_document_field_via_document(self) -> None:
        sql = _compile(
            select(DocumentField).where(DocumentField.__organisation_filter__(TEST_ORG_ID))
        )
        assert "document_field.document_id IN" in sql
        assert "project.organisation_id = 42" in sql

    def test_field_proposal_via_job(self) -> None:
        sql = _compile(
            select(FieldProposal).where(FieldProposal.__organisation_filter__(TEST_ORG_ID))
        )
        assert "field_proposal.job_id IN" in sql
        assert "project.organisation_id = 42" in sql

    def test_user_project_via_user(self) -> None:
        sql = _compile(select(UserProject).where(UserProject.__organisation_filter__(TEST_ORG_ID)))
        assert "user_project.user_id IN" in sql
        assert '"user".organisation_id = 42' in sql

    def test_missing_column_raises(self) -> None:
        # Fail closed : un mixin sans colonne ni override doit lever.
        class Broken(OrganisationScoped):
            pass

        with pytest.raises(NotImplementedError):
            Broken.__organisation_filter__(1)


# ---------------------------------------------------------------------------
# Listener do_orm_execute (CA-2 / CA-4)
# ---------------------------------------------------------------------------


class TestListener:
    def test_applies_filter_when_org_present(self) -> None:
        state = _fake_execute_state(select(Document).where(Document.id == 5), organisation_id=42)
        _apply_organisation_filter(state)
        sql = _compile(state.statement)
        # CA-4 : la ligne d'une autre organisation est exclue -> scalar None -> 404.
        assert "project.organisation_id = 42" in sql

    def test_no_filter_without_org(self) -> None:
        # Service machine / worker : session.info sans organisation_id.
        state = _fake_execute_state(select(Document).where(Document.id == 5), organisation_id=None)
        _apply_organisation_filter(state)
        assert "organisation_id" not in _compile(state.statement)

    def test_skip_flag_disables_filter(self) -> None:
        state = _fake_execute_state(
            select(Document),
            organisation_id=42,
            execution_options={SKIP_ORG_FILTER: True},
        )
        _apply_organisation_filter(state)
        assert "organisation_id" not in _compile(state.statement)

    def test_column_load_is_ignored(self) -> None:
        state = _fake_execute_state(select(Document), organisation_id=42, is_column_load=True)
        _apply_organisation_filter(state)
        assert "organisation_id" not in _compile(state.statement)

    def test_relationship_load_is_ignored(self) -> None:
        state = _fake_execute_state(select(Document), organisation_id=42, is_relationship_load=True)
        _apply_organisation_filter(state)
        assert "organisation_id" not in _compile(state.statement)

    def test_non_select_is_ignored(self) -> None:
        state = _fake_execute_state(select(Document), organisation_id=42, is_select=False)
        _apply_organisation_filter(state)
        assert "organisation_id" not in _compile(state.statement)

    def test_unscoped_table_untouched(self) -> None:
        # file n'est pas scope : aucune clause ajoutee meme avec org active.
        state = _fake_execute_state(select(File).where(File.id == 1), organisation_id=42)
        _apply_organisation_filter(state)
        assert "organisation" not in _compile(state.statement)


# ---------------------------------------------------------------------------
# Cablage session / dependance (CA-1)
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self) -> None:
        self.info: dict = {}

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None


@pytest.fixture
def fake_session_factory(monkeypatch: Any) -> _FakeSession:
    """Remplace la factory de session par un faux, sans driver DB reel."""
    import adam_core.db.session as session_module

    fake = _FakeSession()
    monkeypatch.setattr(session_module, "_async_session_factory", lambda: fake)
    return fake


class TestSessionOrganisationInfo:
    async def test_session_carries_org_id(self, fake_session_factory: _FakeSession) -> None:
        from adam_core.db.session import get_async_session

        async with get_async_session(organisation_id=TEST_ORG_ID) as session:
            assert session.info[SESSION_ORG_KEY] == TEST_ORG_ID

    async def test_session_without_org_is_unscoped(self, fake_session_factory: _FakeSession) -> None:
        from adam_core.db.session import get_async_session

        async with get_async_session() as session:
            assert SESSION_ORG_KEY not in session.info


class TestGetDbCallerWiring:
    def test_user_caller_yields_org(self) -> None:
        from adam_api.dependencies.auth import UserCaller
        from adam_api.dependencies.db import _organisation_id_of

        caller = UserCaller(matricule="MATTEST", organisation_id=TEST_ORG_ID)
        assert _organisation_id_of(caller) == TEST_ORG_ID

    def test_service_caller_yields_none(self) -> None:
        from adam_api.dependencies.auth import ServiceCaller
        from adam_api.dependencies.db import _organisation_id_of

        caller = ServiceCaller(service_name="internal-service")
        assert _organisation_id_of(caller) is None

    @pytest.mark.asyncio
    async def test_get_db_passes_caller_org_to_session(self, monkeypatch: Any) -> None:
        import adam_api.dependencies.db as db_module
        from adam_api.dependencies.auth import UserCaller

        captured: dict = {}

        class _FakeCtx:
            async def __aenter__(self) -> str:
                return "session"

            async def __aexit__(self, *exc: Any) -> None:
                return None

        def fake_get_async_session(organisation_id: Optional[int] = None) -> _FakeCtx:
            captured["organisation_id"] = organisation_id
            return _FakeCtx()

        monkeypatch.setattr(db_module, "get_async_session", fake_get_async_session)

        caller = UserCaller(matricule="MATTEST", organisation_id=TEST_ORG_ID)
        gen = db_module.get_db(caller)
        session = await gen.__anext__()
        assert session == "session"
        assert captured["organisation_id"] == TEST_ORG_ID
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()
