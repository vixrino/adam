"""Resolution du caller a partir du principal porte par le token BdF.

Le token authentifie, la base autorise : ces tests verrouillent la frontiere
entre les deux. Ils remplacent get_async_session par une session factice, la
question posee n'etant pas comment SQLAlchemy execute la requete mais quelle
decision est prise selon la ligne rendue.

Le point le plus important est le code de retour : 403 et jamais 401. Un agent
authentifie par FBI mais absent de `user` a un token parfaitement valide — le
rejeter en 401 l'enverrait chercher un probleme de SSO qui n'existe pas.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

import pytest
from fastapi import HTTPException

from adam_api.dependencies import auth as auth_module
from adam_core.enums.roles import PlatformRole
from adam_core.enums.status import UserStatus

MATRICULE = "I659418"
ORGANISATION_ID = 7


class _Row:
    """Ligne rendue par le SELECT, reduite aux quatre colonnes lues."""

    def __init__(
        self,
        matricule: str = MATRICULE,
        organisation_id: int = ORGANISATION_ID,
        platform_role: Optional[str] = None,
        status: str = UserStatus.ACTIVE.value,
    ) -> None:
        self.matricule = matricule
        self.organisation_id = organisation_id
        self.platform_role = platform_role
        self.status = status


class _Result:
    def __init__(self, row: Optional[_Row]) -> None:
        self._row = row

    def one_or_none(self) -> Optional[_Row]:
        return self._row


class _Session:
    """Session factice qui rend toujours la meme ligne, et retient la requete."""

    def __init__(self, row: Optional[_Row]) -> None:
        self._row = row
        self.executed: list[Any] = []

    async def execute(self, statement: Any) -> _Result:
        self.executed.append(statement)
        return _Result(self._row)


@pytest.fixture(name="session_factory")
def _session_factory(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Remplace get_async_session, et expose la session posee pour inspection."""

    holder: dict[str, _Session] = {}

    def install(row: Optional[_Row]) -> _Session:
        session = _Session(row)
        holder["session"] = session

        @asynccontextmanager
        async def fake_session(**kwargs: Any) -> AsyncIterator[_Session]:
            holder["kwargs"] = kwargs  # type: ignore[assignment]
            yield session

        monkeypatch.setattr(auth_module, "get_async_session", fake_session)
        return session

    install.holder = holder  # type: ignore[attr-defined]
    return install


#: Charge utile reelle d'un token rendu par le mock FBI 2.0.6, reduite aux claims
#: qui nous concernent. Conservee telle quelle : les noms exotiques et le
#: desaccord de casse entre `uid` et `sub` sont ce que le code doit encaisser.
MOCK_CLAIMS = {
    "sub": "I659418",
    "user_name": "I659418",
    "prn": "I659418",
    "uid": "i659418",
    "displayname": "I659418",
    "authorities": ["OPERATOR"],
    "rolesApplicatifs": "OPERATOR",
    "email": "test.operateur@banque-france.fr",
    "iss": "FBI-MOCK-SERVER",
    "client_id": "FBI-Appli-Demo",
    "employeetype": None,
}


class TestPrincipalFromClaims:
    def test_token_du_mock(self) -> None:
        assert auth_module.principal_from_claims(MOCK_CLAIMS) == MATRICULE

    def test_sub_est_prefere(self) -> None:
        """Le sujet RFC 7519 l'emporte : tout emetteur conforme le renseigne."""
        claims = {"sub": "I111111", "prn": "I222222", "user_name": "I333333"}

        assert auth_module.principal_from_claims(claims) == "I111111"

    @pytest.mark.parametrize(
        ("claims", "attendu"),
        [
            ({"prn": "I659418", "user_name": "AUTRE"}, "I659418"),
            ({"user_name": "I659418"}, "I659418"),
        ],
        ids=["repli-sur-prn", "repli-sur-user_name"],
    )
    def test_replis(self, claims: dict[str, Any], attendu: str) -> None:
        assert auth_module.principal_from_claims(claims) == attendu

    def test_uid_n_est_pas_utilise(self) -> None:
        """uid porte la casse saisie par l'agent, il ne fait pas foi."""
        with pytest.raises(HTTPException):
            auth_module.principal_from_claims({"uid": "i659418"})

    @pytest.mark.parametrize(
        "claims",
        [{}, {"sub": ""}, {"sub": "   "}, {"sub": None}, {"sub": 42}, {"sub": ["I659418"]}],
        ids=["vide", "chaine-vide", "espaces", "null", "entier", "liste"],
    )
    def test_401_si_aucun_sujet_exploitable(self, claims: dict[str, Any]) -> None:
        """401 et non 403 : sans sujet, le token n'identifie personne."""
        with pytest.raises(HTTPException) as exc:
            auth_module.principal_from_claims(claims)

        assert exc.value.status_code == 401

    def test_aucune_valeur_de_claim_dans_le_message(self) -> None:
        """Le log ne porte que les noms : un claim peut contenir un email, un NIR."""
        with pytest.raises(HTTPException) as exc:
            auth_module.principal_from_claims({"email": "test@banque-france.fr"})

        assert "banque-france" not in str(exc.value.detail)


class TestCasNominal:
    @pytest.mark.asyncio
    async def test_rend_le_caller_de_la_ligne(self, session_factory: Any) -> None:
        session_factory(_Row(platform_role=PlatformRole.NOTA_ADMIN.value))

        caller = await auth_module.resolve_caller(MATRICULE)

        assert caller.matricule == MATRICULE
        assert caller.organisation_id == ORGANISATION_ID
        assert caller.platform_role == PlatformRole.NOTA_ADMIN.value

    @pytest.mark.asyncio
    async def test_utilisateur_metier_sans_role_de_plateforme(self, session_factory: Any) -> None:
        session_factory(_Row(platform_role=None))

        caller = await auth_module.resolve_caller(MATRICULE)

        assert caller.platform_role is None

    @pytest.mark.asyncio
    async def test_le_matricule_rendu_est_celui_de_la_base(self, session_factory: Any) -> None:
        """Et non celui du token : la base fait foi sur la casse."""
        session_factory(_Row(matricule="I659418"))

        caller = await auth_module.resolve_caller("i659418")

        assert caller.matricule == "I659418"


class TestCasseEtEspaces:
    """Le principal n'est pas garanti normalise par le fournisseur d'identite."""

    @pytest.mark.parametrize("principal", ["i659418", "I659418", "  I659418  ", "I659418\n"])
    @pytest.mark.asyncio
    async def test_variantes_acceptees(self, session_factory: Any, principal: str) -> None:
        session_factory(_Row())

        caller = await auth_module.resolve_caller(principal)

        assert caller.matricule == MATRICULE


class TestRefus:
    @pytest.mark.asyncio
    async def test_403_si_matricule_inconnu(self, session_factory: Any) -> None:
        """403 et non 401 : le token est valide, le compte n'est pas habilite."""
        session_factory(None)

        with pytest.raises(HTTPException) as exc:
            await auth_module.resolve_caller("X999999")

        assert exc.value.status_code == 403

    @pytest.mark.parametrize(
        "status", [UserStatus.INACTIVE.value, UserStatus.SUSPENDED.value]
    )
    @pytest.mark.asyncio
    async def test_403_si_compte_non_actif(self, session_factory: Any, status: str) -> None:
        session_factory(_Row(status=status))

        with pytest.raises(HTTPException) as exc:
            await auth_module.resolve_caller(MATRICULE)

        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_le_matricule_ne_fuit_pas_dans_le_detail(self, session_factory: Any) -> None:
        """Ce chemin est atteignable par tout agent de la Banque : rien d'identifiant."""
        session_factory(None)

        with pytest.raises(HTTPException) as exc:
            await auth_module.resolve_caller("X999999")

        assert "X999999" not in str(exc.value.detail)


class TestSessionNonScopee:
    @pytest.mark.asyncio
    async def test_aucun_filtre_pose_sur_la_session(self, session_factory: Any) -> None:
        """Le filtrage derive du caller : l'appliquer pour le resoudre boucle.

        Si quelqu'un ajoute un scope ici par symetrie avec get_db, plus aucun
        utilisateur ne peut s'authentifier — le SELECT ne verrait que les lignes
        de l'organisation qu'il cherche justement a determiner.
        """
        install = session_factory
        install(_Row())

        await auth_module.resolve_caller(MATRICULE)

        assert install.holder["kwargs"] == {}
