"""Tests unitaires adam_api/routers/projects.py"""

from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.dependencies.auth import UserCaller
from adam_api.routers.projects import router
from adam_core.enums.roles import PlatformRole, ProjectRole

_NOW = datetime(2026, 6, 26, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def app() -> FastAPI:
    fastapi_app = FastAPI()
    fastapi_app.include_router(router)
    return fastapi_app


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock(side_effect=lambda obj: setattr(obj, "id", 1))
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result
    db.get.return_value = None
    return db


@pytest.fixture
def caller() -> UserCaller:
    """Appelant metier par defaut : POST /projects l'inscrit sur le projet cree."""
    return UserCaller(matricule="MATTEST", organisation_id=1)


@pytest.fixture
def client(app: FastAPI, mock_db: AsyncMock, caller: UserCaller) -> TestClient:
    from adam_api.dependencies.auth import get_caller
    from adam_api.dependencies.db import get_db

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_caller] = lambda: caller
    return TestClient(app, raise_server_exceptions=False)


def _make_project(
    id: int = 1, name: str = "Projet", organisation_id: int = 1, status: str = "ACTIVE"
) -> MagicMock:
    row = MagicMock()
    row.id = id
    row.name = name
    row.organisation_id = organisation_id
    row.status = status
    row.updated_at = _NOW
    return row


def _make_up(user_id: int = 5, project_id: int = 1, role: str = "OPERATOR") -> MagicMock:
    up = MagicMock()
    up.user_id = user_id
    up.project_id = project_id
    up.role = role
    up.updated_at = _NOW
    return up


# ---------------------------------------------------------------------------
# GET /projects
# ---------------------------------------------------------------------------


class TestListProjects:
    def test_returns_200(self, client: TestClient) -> None:
        assert client.get("/projects").status_code == 200

    def test_returns_empty_list(self, client: TestClient) -> None:
        assert client.get("/projects").json() == []

    def test_returns_list(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_project(id=1, name="P1"),
            _make_project(id=2, name="P2"),
        ]
        data = client.get("/projects").json()
        assert len(data) == 2
        assert data[0]["name"] == "P1"

    def test_filter_by_organisation_id(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            _make_project(organisation_id=3)
        ]
        data = client.get("/projects?organisation_id=3").json()
        assert data[0]["organisation_id"] == 3


# ---------------------------------------------------------------------------
# GET /projects/{project_id}
# ---------------------------------------------------------------------------


class TestGetProject:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        assert client.get("/projects/1").status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.get("/projects/99").status_code == 404

    def test_response_contains_status_and_updated_at(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        mock_db.get.return_value = _make_project(id=1, status="ARCHIVED")
        data = client.get("/projects/1").json()
        assert data["status"] == "ARCHIVED"
        assert "updated_at" in data


# ---------------------------------------------------------------------------
# POST /projects
# ---------------------------------------------------------------------------


class TestCreateProject:
    """RACI de gouvernance : "creer et gerer les organisations et projets" est R
    pour l'Administrateur NOTA et I pour les trois autres acteurs. La ligne
    suivante, "gerer les projets", est celle de l'Administrateur Metier et porte
    sur un projet existant.
    """

    @pytest.fixture
    def caller(self) -> UserCaller:
        return UserCaller(
            matricule="MATADMIN",
            organisation_id=1,
            platform_role=PlatformRole.NOTA_ADMIN.value,
        )

    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        assert (
            client.post("/projects", json={"organisation_id": 1, "name": "Nouveau"}).status_code
            == 201
        )

    def test_422_when_missing_name(self, client: TestClient) -> None:
        assert client.post("/projects", json={"organisation_id": 1}).status_code == 422

    def test_422_when_missing_organisation_id(self, client: TestClient) -> None:
        assert client.post("/projects", json={"name": "P"}).status_code == 422

    def test_no_membership_is_created(self, client: TestClient, mock_db: AsyncMock) -> None:
        # L'Administrateur NOTA porte deja la lecture transverse : aucune
        # adhesion a poser, le projet nait sans membre.
        client.post("/projects", json={"organisation_id": 1, "name": "Nouveau"})
        mock_db.execute.assert_not_called()


class TestCreateProjectForbidden:
    @pytest.mark.parametrize(
        "platform_role",
        [None, PlatformRole.NOTA_SUPERVISOR.value, ProjectRole.BUSINESS_ADMIN.value],
        ids=["operateur-ou-admin-metier", "superviseur-nota", "role-projet-egare"],
    )
    def test_403_for_non_nota_admin(
        self, app: FastAPI, mock_db: AsyncMock, platform_role: Optional[str]
    ) -> None:
        from adam_api.dependencies.auth import get_caller
        from adam_api.dependencies.db import get_db

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_caller] = lambda: UserCaller(
            matricule="MATBIZ", organisation_id=1, platform_role=platform_role
        )
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/projects", json={"organisation_id": 1, "name": "P"})
        assert response.status_code == 403

    def test_service_caller_is_allowed(self, app: FastAPI, mock_db: AsyncMock) -> None:
        # Provisionnement et workers : le RACI decrit des acteurs humains, il ne
        # regit pas les services machine.
        from adam_api.dependencies.auth import ServiceCaller, get_caller
        from adam_api.dependencies.db import get_db

        app.dependency_overrides[get_db] = lambda: mock_db
        app.dependency_overrides[get_caller] = lambda: ServiceCaller(service_name="provisioning")
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/projects", json={"organisation_id": 1, "name": "P"})
        assert response.status_code == 201


# ---------------------------------------------------------------------------
# POST /projects/{project_id}/users
# ---------------------------------------------------------------------------


class TestAddUserToProject:
    def test_returns_201(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        assert client.post("/projects/1/users", json={"user_id": 5}).status_code == 201

    def test_404_when_project_not_found(self, client: TestClient) -> None:
        assert client.post("/projects/99/users", json={"user_id": 1}).status_code == 404

    def test_response_contains_role(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        data = client.post(
            "/projects/1/users", json={"user_id": 5, "role": "BUSINESS_ADMIN"}
        ).json()
        assert data["role"] == "BUSINESS_ADMIN"
        assert data["project_id"] == 1
        assert data["user_id"] == 5


# ---------------------------------------------------------------------------
# PATCH /projects/{project_id}
# ---------------------------------------------------------------------------


class TestPatchProject:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        assert client.patch("/projects/1", json={"name": "Nouveau"}).status_code == 200

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.patch("/projects/99", json={"name": "X"}).status_code == 404

    def test_422_on_invalid_status(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        assert client.patch("/projects/1", json={"status": "INVALID"}).status_code == 422

    def test_valid_status_accepted(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        assert client.patch("/projects/1", json={"status": "ARCHIVED"}).status_code == 200

    def test_response_contains_updated_at(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.get.return_value = _make_project(id=1)
        data = client.patch("/projects/1", json={"name": "X"}).json()
        assert "updated_at" in data


# ---------------------------------------------------------------------------
# PATCH /projects/{project_id}/users/{user_id}
# ---------------------------------------------------------------------------


class TestUpdateUserRole:
    def test_returns_200(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_up()
        assert (
            client.patch("/projects/1/users/5", json={"role": "BUSINESS_ADMIN"}).status_code == 200
        )

    def test_404_when_user_not_in_project(self, client: TestClient) -> None:
        assert client.patch("/projects/1/users/99", json={"role": "OPERATOR"}).status_code == 404

    def test_422_on_invalid_role(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_up()
        assert client.patch("/projects/1/users/5", json={"role": "INVALID"}).status_code == 422

    def test_response_contains_role_and_updated_at(
        self, client: TestClient, mock_db: AsyncMock
    ) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_up(role="OPERATOR")
        data = client.patch("/projects/1/users/5", json={"role": "BUSINESS_ADMIN"}).json()
        assert "role" in data
        assert "updated_at" in data
        assert data["user_id"] == 5
        assert data["project_id"] == 1


# ---------------------------------------------------------------------------
# DELETE /projects/{project_id}/users/{user_id}
# ---------------------------------------------------------------------------


class TestRemoveUserFromProject:
    def test_returns_204(self, client: TestClient, mock_db: AsyncMock) -> None:
        mock_db.execute.return_value.scalar_one_or_none.return_value = _make_up()
        assert client.delete("/projects/1/users/5").status_code == 204

    def test_404_when_not_found(self, client: TestClient) -> None:
        assert client.delete("/projects/1/users/99").status_code == 404
