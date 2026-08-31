"""Tests du second etage de filtrage : restriction aux projets de l'appelant.

Le filtre organisation seul laisse un utilisateur voir tous les projets de son
organisation. Le mixin ProjectScoped ajoute une restriction aux seules adhesions
lues dans user_project. Ces tests couvrent :

    CA-1 : recensement des tables ProjectScoped, et de celles volontairement
           laissees hors du second etage (organisation, user, file).
    CA-2 : le critere de chaque table remonte bien jusqu'a user_project.
    CA-3 : les deux etages se cumulent en AND sans se remplacer.
    CA-4 : le second etage ne se declenche que si un matricule est en session.
    CA-5 : get_db ne pose de matricule que pour un utilisateur metier.
    CA-6 : les sous-requetes d'adhesion restent au niveau Core, hors de portee
           de with_loader_criteria.
"""

from types import SimpleNamespace
from typing import Any, Optional

import pytest
from sqlalchemy import select
from sqlalchemy.orm import with_loader_criteria

import adam_core.models  # noqa: F401 - force le mapping de tous les modeles
from adam_core.db.scoping import (
    SESSION_MATRICULE_KEY,
    SESSION_ORG_KEY,
    SKIP_ORG_FILTER,
    OrganisationScoped,
    ProjectScoped,
    _apply_organisation_filter,
    _iter_project_scoped_models,
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

TEST_ORG_ID = 42
TEST_MATRICULE = "MAT00042"

# Fragment identifiant la sous-requete d'adhesion, present dans tout critere du
# second etage quelle que soit la longueur de la chaine de FK remontee.
MEMBERSHIP_SQL = "\"user\".matricule = 'MAT00042'"

# Fragment de l'echappatoire de lecture transverse accordee a l'Administrateur
# Metier par le tableau de controle d'acces.
TRANSVERSE_SQL = "user_project.role = 'BUSINESS_ADMIN'"


def _compile(stmt: Any) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def _fake_execute_state(
    statement: Any,
    *,
    organisation_id: Optional[int] = None,
    matricule: Optional[str] = None,
    is_select: bool = True,
    is_column_load: bool = False,
    is_relationship_load: bool = False,
    execution_options: Optional[dict[str, Any]] = None,
) -> SimpleNamespace:
    """Imite un ORMExecuteState pour tester le listener sans base reelle."""
    info: dict[str, Any] = {}
    if organisation_id is not None:
        info[SESSION_ORG_KEY] = organisation_id
    if matricule is not None:
        info[SESSION_MATRICULE_KEY] = matricule
    return SimpleNamespace(
        statement=statement,
        is_select=is_select,
        is_column_load=is_column_load,
        is_relationship_load=is_relationship_load,
        execution_options=execution_options or {},
        session=SimpleNamespace(info=info),
    )


# ---------------------------------------------------------------------------
# Recensement (CA-1)
# ---------------------------------------------------------------------------


class TestProjectScopedRegistry:
    def test_project_derived_tables_are_scoped(self) -> None:
        scoped = set(_iter_project_scoped_models())
        assert {
            Project,
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

    def test_organisation_is_not_project_scoped(self) -> None:
        # L'appelant doit pouvoir lire sa propre organisation, qui n'appartient
        # a aucun projet.
        assert not issubclass(Organisation, ProjectScoped)
        assert Organisation not in set(_iter_project_scoped_models())

    def test_user_is_not_project_scoped(self) -> None:
        # Le referentiel des utilisateurs de l'organisation reste lisible :
        # le restreindre aux co-equipiers casserait l'affectation a un projet.
        assert not issubclass(User, ProjectScoped)
        assert User not in set(_iter_project_scoped_models())

    def test_file_is_not_project_scoped(self) -> None:
        assert not issubclass(File, ProjectScoped)

    def test_every_project_scoped_model_has_working_filter(self) -> None:
        # Fail closed : aucune table du second etage ne reste sans critere.
        for model in _iter_project_scoped_models():
            sql = _compile(
                select(model).options(
                    with_loader_criteria(model, model.__project_filter__(TEST_MATRICULE))
                )
            )
            assert MEMBERSHIP_SQL in sql

    def test_missing_column_raises(self) -> None:
        class Broken(ProjectScoped):
            pass

        with pytest.raises(NotImplementedError):
            Broken.__project_filter__(TEST_MATRICULE)


# ---------------------------------------------------------------------------
# Criteres par table (CA-2)
# ---------------------------------------------------------------------------


class TestProjectFilters:
    def test_project_filters_on_own_id(self) -> None:
        sql = _compile(select(Project).where(Project.__project_filter__(TEST_MATRICULE)))
        assert "project.id IN" in sql
        assert MEMBERSHIP_SQL in sql

    def test_dataset_direct_project_column(self) -> None:
        sql = _compile(select(Dataset).where(Dataset.__project_filter__(TEST_MATRICULE)))
        assert "dataset.project_id IN" in sql
        assert MEMBERSHIP_SQL in sql

    def test_doc_schema_direct_project_column(self) -> None:
        sql = _compile(select(DocSchema).where(DocSchema.__project_filter__(TEST_MATRICULE)))
        assert "doc_schema.project_id IN" in sql

    def test_user_project_direct_project_column(self) -> None:
        sql = _compile(select(UserProject).where(UserProject.__project_filter__(TEST_MATRICULE)))
        assert "user_project.project_id IN" in sql

    def test_document_via_dataset(self) -> None:
        sql = _compile(select(Document).where(Document.__project_filter__(TEST_MATRICULE)))
        assert "document.dataset_id IN" in sql
        assert "dataset.project_id IN" in sql
        assert MEMBERSHIP_SQL in sql

    def test_job_via_dataset(self) -> None:
        sql = _compile(select(Job).where(Job.__project_filter__(TEST_MATRICULE)))
        assert "job.dataset_id IN" in sql
        assert MEMBERSHIP_SQL in sql

    def test_ocr_result_via_dataset(self) -> None:
        sql = _compile(select(OcrResult).where(OcrResult.__project_filter__(TEST_MATRICULE)))
        assert "ocr_result.dataset_id IN" in sql
        assert MEMBERSHIP_SQL in sql

    def test_field_spec_via_doc_schema(self) -> None:
        sql = _compile(select(FieldSpec).where(FieldSpec.__project_filter__(TEST_MATRICULE)))
        assert "field_spec.schema_id IN" in sql
        assert "doc_schema.project_id IN" in sql

    def test_document_field_via_document(self) -> None:
        sql = _compile(
            select(DocumentField).where(DocumentField.__project_filter__(TEST_MATRICULE))
        )
        assert "document_field.document_id IN" in sql
        assert MEMBERSHIP_SQL in sql

    def test_field_proposal_via_job(self) -> None:
        sql = _compile(
            select(FieldProposal).where(FieldProposal.__project_filter__(TEST_MATRICULE))
        )
        assert "field_proposal.job_id IN" in sql
        assert MEMBERSHIP_SQL in sql

    def test_membership_subquery_joins_user_project(self) -> None:
        # CA-2 : la restriction se lit bien dans user_project, pas ailleurs.
        sql = _compile(select(Project).where(Project.__project_filter__(TEST_MATRICULE)))
        assert "SELECT user_project.project_id" in sql
        assert 'JOIN "user" ON "user".id = user_project.user_id' in sql


class TestTransverseReadOfBusinessAdmin:
    """Controle d'acces : lecture transverse Non / Oui (projets) / Oui / Oui.

    Seul l'Operateur Metier est restreint a ses adhesions. L'Administrateur
    Metier voit les projets de son organisation, les deux roles NOTA etant deja
    hors filtre par une session non scopee.
    """

    def test_le_filtre_porte_une_echappatoire_business_admin(self) -> None:
        sql = _compile(select(Project).where(Project.__project_filter__(TEST_MATRICULE)))
        assert TRANSVERSE_SQL in sql
        assert "EXISTS" in sql

    def test_echappatoire_en_or_et_non_en_and(self) -> None:
        # En AND, elle restreindrait au lieu d'elargir : l'Administrateur Metier
        # ne verrait plus que ses propres adhesions, et l'Operateur plus rien.
        sql = _compile(select(Project).where(Project.__project_filter__(TEST_MATRICULE)))
        adhesion = sql.index("SELECT user_project.project_id")
        exists = sql.index("EXISTS")
        assert " OR " in sql[adhesion:exists]

    def test_toutes_les_chaines_heritent_de_l_echappatoire(self) -> None:
        # member_project_ids est le point de passage unique : la distinction
        # Operateur / Administrateur Metier n'est exprimee qu'une fois.
        for model in _iter_project_scoped_models():
            sql = _compile(select(model).where(model.__project_filter__(TEST_MATRICULE)))
            assert TRANSVERSE_SQL in sql, model.__name__

    def test_seul_business_admin_ouvre_la_lecture_transverse(self) -> None:
        # OPERATOR ne doit pas figurer dans l'echappatoire : l'operateur est le
        # seul acteur a qui le tableau refuse la lecture transverse.
        sql = _compile(select(Project).where(Project.__project_filter__(TEST_MATRICULE)))
        assert "'OPERATOR'" not in sql


# ---------------------------------------------------------------------------
# Listener : cumul des deux etages (CA-3 / CA-4)
# ---------------------------------------------------------------------------


class TestListenerBothStages:
    def test_both_filters_are_applied(self) -> None:
        state = _fake_execute_state(
            select(Document).where(Document.id == 5),
            organisation_id=TEST_ORG_ID,
            matricule=TEST_MATRICULE,
        )
        _apply_organisation_filter(state)
        sql = _compile(state.statement)
        # CA-3 : le second etage s'ajoute au premier, il ne le remplace pas.
        assert "project.organisation_id = 42" in sql
        assert MEMBERSHIP_SQL in sql

    def test_org_only_when_no_matricule(self) -> None:
        # Cas d'un role plateforme neutralise cote get_db, ou d'une session
        # ouverte sans matricule : le premier etage seul.
        state = _fake_execute_state(select(Document), organisation_id=TEST_ORG_ID)
        sql = _compile_after(state)
        assert "project.organisation_id = 42" in sql
        assert "matricule" not in sql

    def test_project_only_when_no_org(self) -> None:
        # Les deux etages sont independants : le second n'exige pas le premier.
        state = _fake_execute_state(select(Document), matricule=TEST_MATRICULE)
        sql = _compile_after(state)
        assert MEMBERSHIP_SQL in sql
        assert "organisation_id" not in sql

    def test_no_filter_without_any_scope(self) -> None:
        # Service machine / worker : ni organisation ni matricule.
        state = _fake_execute_state(select(Document).where(Document.id == 5))
        sql = _compile_after(state)
        assert "organisation_id" not in sql
        assert "matricule" not in sql

    def test_skip_flag_disables_both_stages(self) -> None:
        state = _fake_execute_state(
            select(Document),
            organisation_id=TEST_ORG_ID,
            matricule=TEST_MATRICULE,
            execution_options={SKIP_ORG_FILTER: True},
        )
        sql = _compile_after(state)
        assert "organisation_id" not in sql
        assert "matricule" not in sql

    def test_column_load_is_ignored(self) -> None:
        state = _fake_execute_state(
            select(Document), matricule=TEST_MATRICULE, is_column_load=True
        )
        assert "matricule" not in _compile_after(state)

    def test_relationship_load_is_ignored(self) -> None:
        state = _fake_execute_state(
            select(Document), matricule=TEST_MATRICULE, is_relationship_load=True
        )
        assert "matricule" not in _compile_after(state)

    def test_non_select_is_ignored(self) -> None:
        state = _fake_execute_state(select(Document), matricule=TEST_MATRICULE, is_select=False)
        assert "matricule" not in _compile_after(state)

    def test_unscoped_table_untouched(self) -> None:
        state = _fake_execute_state(select(File).where(File.id == 1), matricule=TEST_MATRICULE)
        assert "matricule" not in _compile_after(state)

    def test_user_table_untouched_by_project_stage(self) -> None:
        # Le referentiel utilisateurs reste filtre par organisation seule.
        state = _fake_execute_state(
            select(User), organisation_id=TEST_ORG_ID, matricule=TEST_MATRICULE
        )
        sql = _compile_after(state)
        assert '"user".organisation_id = 42' in sql
        assert MEMBERSHIP_SQL not in sql


def _compile_after(state: SimpleNamespace) -> str:
    _apply_organisation_filter(state)
    return _compile(state.statement)


# ---------------------------------------------------------------------------
# Sous-requetes au niveau Core (CA-6)
# ---------------------------------------------------------------------------


class TestMembershipSubqueriesStayCore:
    """Les sous-requetes d'adhesion doivent echapper a with_loader_criteria.

    Baties sur les classes ORM, elles verraient leur propre critere re-injecte
    a l'interieur d'elles-memes : user_project est ProjectScoped, donc defini en
    termes de user_project. Le niveau Core (``__table__``) coupe la boucle.
    """

    def test_membership_subquery_is_not_re_filtered(self) -> None:
        state = _fake_execute_state(select(UserProject), matricule=TEST_MATRICULE)
        sql = _compile_after(state)
        # Exactement deux occurrences, celles que member_project_ids contient
        # par construction : la liste des adhesions et le EXISTS de lecture
        # transverse. Toute occurrence supplementaire signalerait que
        # with_loader_criteria a re-injecte le critere de UserProject dans sa
        # propre definition.
        assert sql.count(MEMBERSHIP_SQL) == 2
        assert sql.count(TRANSVERSE_SQL) == 1

    def test_org_subquery_is_not_re_filtered(self) -> None:
        state = _fake_execute_state(select(Document), organisation_id=TEST_ORG_ID)
        sql = _compile_after(state)
        assert sql.count("project.organisation_id = 42") == 1


# ---------------------------------------------------------------------------
# Cablage get_db (CA-5)
# ---------------------------------------------------------------------------


class TestGetDbMatriculeWiring:
    def test_user_caller_yields_matricule(self) -> None:
        from adam_api.dependencies.auth import UserCaller
        from adam_api.dependencies.db import _matricule_of

        caller = UserCaller(matricule=TEST_MATRICULE, organisation_id=TEST_ORG_ID)
        assert _matricule_of(caller) == TEST_MATRICULE

    def test_service_caller_yields_none(self) -> None:
        from adam_api.dependencies.auth import ServiceCaller
        from adam_api.dependencies.db import _matricule_of

        assert _matricule_of(ServiceCaller(service_name="internal-service")) is None

    @pytest.mark.parametrize("role", ["NOTA_ADMIN", "NOTA_SUPERVISOR"])
    def test_platform_roles_yield_none(self, role: str) -> None:
        # Un role plateforme traverse les projets comme il traverse les
        # organisations : les deux etages sont neutralises ensemble.
        from adam_api.dependencies.auth import UserCaller
        from adam_api.dependencies.db import _matricule_of

        caller = UserCaller(
            matricule="MATADMIN", organisation_id=TEST_ORG_ID, platform_role=role
        )
        assert _matricule_of(caller) is None

    def test_project_role_dans_platform_role_ne_neutralise_pas(self) -> None:
        """Un ProjectRole pose par erreur dans platform_role reste scope.

        La lecture transverse de l'Administrateur Metier est accordee en SQL,
        pas ici : get_db pose le matricule pour tout utilisateur metier, et
        member_project_ids decide ensuite de l'etendue. Une valeur de
        ProjectRole dans ce champ ne doit donc rien neutraliser.
        """
        from adam_api.dependencies.auth import UserCaller
        from adam_api.dependencies.db import _matricule_of
        from adam_core.enums.roles import ProjectRole

        caller = UserCaller(
            matricule=TEST_MATRICULE,
            organisation_id=TEST_ORG_ID,
            platform_role=ProjectRole.BUSINESS_ADMIN.value,
        )
        assert _matricule_of(caller) == TEST_MATRICULE

    def test_valeur_inconnue_ne_neutralise_pas_le_filtre(self) -> None:
        from adam_api.dependencies.auth import UserCaller
        from adam_api.dependencies.db import _matricule_of

        caller = UserCaller(
            matricule=TEST_MATRICULE, organisation_id=TEST_ORG_ID, platform_role="SUPERADMIN"
        )
        assert _matricule_of(caller) == TEST_MATRICULE

    @pytest.mark.asyncio
    async def test_get_db_passes_both_to_session(self, monkeypatch: Any) -> None:
        import adam_api.dependencies.db as db_module
        from adam_api.dependencies.auth import UserCaller

        captured: dict[str, Any] = {}

        class _FakeCtx:
            async def __aenter__(self) -> str:
                return "session"

            async def __aexit__(self, *exc: Any) -> None:
                return None

        def fake_get_async_session(
            organisation_id: Optional[int] = None, matricule: Optional[str] = None
        ) -> _FakeCtx:
            captured["organisation_id"] = organisation_id
            captured["matricule"] = matricule
            return _FakeCtx()

        monkeypatch.setattr(db_module, "get_async_session", fake_get_async_session)

        caller = UserCaller(matricule=TEST_MATRICULE, organisation_id=TEST_ORG_ID)
        gen = db_module.get_db(caller)
        assert await gen.__anext__() == "session"
        assert captured == {"organisation_id": TEST_ORG_ID, "matricule": TEST_MATRICULE}
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()


class TestSessionMatriculeInfo:
    async def test_session_carries_matricule(self, fake_session_factory: Any) -> None:
        from adam_core.db.session import get_async_session

        async with get_async_session(
            organisation_id=TEST_ORG_ID, matricule=TEST_MATRICULE
        ) as session:
            assert session.info[SESSION_MATRICULE_KEY] == TEST_MATRICULE

    async def test_session_without_matricule_is_unrestricted(
        self, fake_session_factory: Any
    ) -> None:
        from adam_core.db.session import get_async_session

        async with get_async_session(organisation_id=TEST_ORG_ID) as session:
            assert SESSION_MATRICULE_KEY not in session.info


class _FakeSession:
    def __init__(self) -> None:
        self.info: dict[str, Any] = {}

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


# Le mixin OrganisationScoped reste importe pour verifier que les deux etages
# sont bien distincts et non confondus dans la hierarchie.
def test_les_deux_mixins_sont_independants() -> None:
    assert not issubclass(ProjectScoped, OrganisationScoped)
    assert not issubclass(OrganisationScoped, ProjectScoped)
