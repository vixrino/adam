"""Creation de la ligne `user` depuis l'AD a la premiere connexion (GET /users/me).

L'AD est simule comme dans test_annuaire.py, et la base par une session factice
qui rend, dans l'ordre, les resultats prepares : la question n'est pas comment
SQLAlchemy execute les requetes, mais quelle decision est prise selon ce que
l'AD et la base repondent.
"""

from __future__ import annotations

import importlib
import pkgutil
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, AsyncIterator, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from adam_api import routers
from adam_api.dependencies import auth as auth_module
from adam_api.dependencies.auth import UserCaller, require_user_premiere_connexion
from adam_api.dependencies.db import get_db_premiere_connexion
from adam_api.routers.users import me_router
from adam_api.services import premiere_connexion as service
from adam_api.services.annuaire import AnnuaireErreur, PersonneAnnuaire
from adam_core.enums.status import UserStatus

MATRICULE = "I21080M"

DANIEL = PersonneAnnuaire(
    matricule=MATRICULE,
    nom_affiche="Daniel Ferreira Lara",
    email="daniel.ferreira@exemple.fr",
    prenom="Daniel",
    nom="Ferreira Lara",
    departement="RE1 US2183 DGSI DIRES SOLAPS",
)


class _AnnuaireFactice:
    def __init__(self, personnes: List[PersonneAnnuaire], erreur: bool = False) -> None:
        self.personnes = personnes
        self.erreur = erreur

    async def rechercher(self, texte: str) -> List[PersonneAnnuaire]:
        return self.personnes

    async def trouver(self, matricule: str) -> Optional[PersonneAnnuaire]:
        if self.erreur:
            raise AnnuaireErreur("injoignable")
        return next((p for p in self.personnes if p.matricule == matricule.upper()), None)


def _resultat(*, first: Any = None, all_: Any = None) -> MagicMock:
    r = MagicMock()
    r.first.return_value = first
    r.all.return_value = all_ or []
    return r


ORGANISATIONS = _resultat(all_=[("dgsi", 3), ("dires", 5)])
MAIL_LIBRE = _resultat(first=None)


def _session(*resultats: MagicMock, flush: Any = None) -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(side_effect=list(resultats))
    db.flush = AsyncMock(side_effect=flush)
    return db


@pytest.fixture(name="base")
def _base(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Remplace la session du service par une session factice."""

    def installer(db: AsyncMock) -> AsyncMock:
        @asynccontextmanager
        async def fausse_session(**_: Any) -> AsyncIterator[AsyncMock]:
            yield db

        monkeypatch.setattr(service, "get_async_session", fausse_session)
        return db

    return installer


# -- Organisation ----------------------------------------------------------------------


class TestOrganisation:
    def test_mots_du_departement_en_minuscules(self) -> None:
        assert service.slugs_candidats("RE1 US2183 DGSI DIRES SOLAPS") == [
            "re1",
            "us2183",
            "dgsi",
            "dires",
            "solaps",
        ]

    def test_departement_vide(self) -> None:
        assert not service.slugs_candidats(None)
        assert not service.slugs_candidats("  ")

    async def test_le_mot_le_plus_precis_l_emporte(self) -> None:
        db = _session(ORGANISATIONS)
        assert await service.organisation_du_departement(db, DANIEL.departement) == 5

    async def test_aucun_slug_connu(self) -> None:
        db = _session(_resultat(all_=[]))
        assert await service.organisation_du_departement(db, DANIEL.departement) is None


    async def test_slug_compare_sans_casse(self) -> None:
        db = _session(_resultat(all_=[("DIRES", 5)]))
        assert await service.organisation_du_departement(db, DANIEL.departement) == 5

    async def test_repli_sur_l_organisation_par_defaut(self) -> None:
        """Seule la Banque de France existe, sous le slug BDF."""
        db = _session(_resultat(all_=[("BDF", 1)]))
        departement = "RE1-2183 DGSI DIRES SOLAPS"
        assert await service.organisation_du_departement(db, departement, "BDF") == 1

    async def test_le_departement_prime_sur_le_repli(self) -> None:
        db = _session(_resultat(all_=[("BDF", 1), ("dires", 5)]))
        assert await service.organisation_du_departement(db, DANIEL.departement, "bdf") == 5

    async def test_sans_departement_la_base_n_est_pas_interrogee(self) -> None:
        db = _session()
        assert await service.organisation_du_departement(db, None) is None
        db.execute.assert_not_called()


# -- Creation --------------------------------------------------------------------------


class TestCreation:
    async def test_operateur_cree_depuis_la_fiche_ad(self, base: Any) -> None:
        db = base(_session(ORGANISATIONS, MAIL_LIBRE))

        cree = await service.creer_a_la_premiere_connexion("i21080m", _AnnuaireFactice([DANIEL]))

        assert cree is True
        user = db.add.call_args.args[0]
        assert user.matricule == MATRICULE
        assert user.full_name == "Daniel Ferreira Lara"
        assert user.email == "daniel.ferreira@exemple.fr"
        assert user.status == UserStatus.ACTIVE.value
        assert user.organisation_id == 5
        assert user.platform_role is None
        assert not user.user_projects

    async def test_inconnu_ou_desactive_dans_l_ad(self, base: Any) -> None:
        db = base(_session())
        assert await service.creer_a_la_premiere_connexion(MATRICULE, _AnnuaireFactice([])) is False
        db.add.assert_not_called()

    async def test_organisation_inconnue(self, base: Any) -> None:
        db = base(_session(_resultat(all_=[])))
        with pytest.raises(service.OrganisationInconnue, match="DGSI DIRES"):
            await service.creer_a_la_premiere_connexion(MATRICULE, _AnnuaireFactice([DANIEL]))
        db.add.assert_not_called()

    async def test_sans_adresse_mail(self, base: Any) -> None:
        sans_mail = PersonneAnnuaire(MATRICULE, "Sans Mail", None, None, None, "DGSI")
        db = base(_session(ORGANISATIONS))
        with pytest.raises(service.SansAdresseMail):
            await service.creer_a_la_premiere_connexion(MATRICULE, _AnnuaireFactice([sans_mail]))
        db.add.assert_not_called()

    async def test_adresse_deja_portee(self, base: Any) -> None:
        db = base(_session(ORGANISATIONS, _resultat(first=(42,))))
        with pytest.raises(service.AdresseMailPrise):
            await service.creer_a_la_premiere_connexion(MATRICULE, _AnnuaireFactice([DANIEL]))
        db.add.assert_not_called()

    async def test_creation_concurrente(self, base: Any) -> None:
        """Le second appel bute sur l'unicite du matricule : la ligne existe."""
        doublon = IntegrityError("INSERT", {}, Exception("duplicate key"))
        base(_session(ORGANISATIONS, MAIL_LIBRE, flush=doublon))
        assert await service.creer_a_la_premiere_connexion(MATRICULE, _AnnuaireFactice([DANIEL]))


# -- Codes de retour -------------------------------------------------------------------


@pytest.fixture(name="ad")
def _ad(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Remplace l'annuaire configure et la creation par des comportements imposes."""

    def installer(effet: Any) -> AsyncMock:
        monkeypatch.setattr(auth_module, "annuaire_depuis_settings", lambda _: object())
        creer = AsyncMock(side_effect=effet if isinstance(effet, Exception) else None)
        if not isinstance(effet, Exception):
            creer.return_value = effet
        monkeypatch.setattr(auth_module, "creer_a_la_premiere_connexion", creer)
        return creer

    return installer


class TestCodesDeRetour:
    async def test_sans_adresse_mail_403(self, ad: Any) -> None:
        ad(service.SansAdresseMail("x"))
        with pytest.raises(HTTPException) as exc:
            await auth_module.creer_depuis_annuaire(MATRICULE)
        assert exc.value.status_code == 403

    async def test_adresse_prise_409(self, ad: Any) -> None:
        ad(service.AdresseMailPrise("x"))
        with pytest.raises(HTTPException) as exc:
            await auth_module.creer_depuis_annuaire(MATRICULE)
        assert exc.value.status_code == 409

    @pytest.mark.parametrize(
        "effet",
        [False, service.OrganisationInconnue("x"), AnnuaireErreur("injoignable")],
        ids=["inconnu-de-l-ad", "organisation-inconnue", "ad-injoignable"],
    )
    async def test_rien_n_est_cree_le_403_vient_de_resolve_caller(
        self, ad: Any, effet: Any
    ) -> None:
        ad(effet)
        assert await auth_module.creer_depuis_annuaire(MATRICULE) is None

    async def test_ad_desactive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(auth_module.settings, "ad_enabled", False)
        creer = AsyncMock()
        monkeypatch.setattr(auth_module, "creer_a_la_premiere_connexion", creer)
        assert await auth_module.creer_depuis_annuaire(MATRICULE) is None
        creer.assert_not_called()


# -- resolve_caller --------------------------------------------------------------------


@pytest.fixture(name="lignes")
def _lignes(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """La table `user` rend successivement les lignes donnees (None = absente)."""

    def installer(*rangs: Optional[SimpleNamespace]) -> None:
        monkeypatch.setattr(auth_module, "_ligne_utilisateur", AsyncMock(side_effect=list(rangs)))

    return installer


#: Ligne `user` telle que resolve_caller la lit. `id` et les dates n'existent pas
#: dans toutes les versions du SELECT : les porter evite qu'un ajout de colonne
#: casse ces tests, qui portent sur la creation et non sur le contenu du caller.
LIGNE = SimpleNamespace(
    id=99,
    matricule=MATRICULE,
    organisation_id=5,
    platform_role=None,
    status=UserStatus.ACTIVE.value,
    deleted_at=None,
    last_login_at=None,
)


class TestResolveCaller:
    async def test_inconnu_cree_puis_relu(self, lignes: Any) -> None:
        lignes(None, LIGNE)
        createur = AsyncMock()

        caller = await auth_module.resolve_caller(MATRICULE, createur)

        createur.assert_awaited_once_with(MATRICULE)
        assert (caller.matricule, caller.organisation_id) == (MATRICULE, 5)

    async def test_deja_en_base_rien_n_est_cree(self, lignes: Any) -> None:
        lignes(LIGNE)
        createur = AsyncMock()
        await auth_module.resolve_caller(MATRICULE, createur)
        createur.assert_not_called()

    async def test_creation_impossible_403(self, lignes: Any) -> None:
        lignes(None, None)
        with pytest.raises(HTTPException) as exc:
            await auth_module.resolve_caller(MATRICULE, AsyncMock())
        assert exc.value.status_code == 403
        assert exc.value.detail == "Compte non habilite sur cette application"

    async def test_sans_createur_un_inconnu_reste_refuse(self, lignes: Any) -> None:
        lignes(None)
        with pytest.raises(HTTPException) as exc:
            await auth_module.resolve_caller(MATRICULE)
        assert exc.value.status_code == 403

    async def test_bypass_dev_ne_cree_rien(
        self, lignes: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(auth_module.settings, "api_disable_jwt_validation", True)
        monkeypatch.setattr(auth_module.settings, "api_dev_matricule", MATRICULE)
        lignes(None)
        createur = AsyncMock()
        with pytest.raises(HTTPException):
            await auth_module._identifier(  # pylint: disable=protected-access
                MagicMock(), jwt=None, api_key=None, createur=createur
            )
        createur.assert_not_called()


USER = SimpleNamespace(
    id=99,
    email=DANIEL.email,
    full_name=DANIEL.nom_affiche,
    matricule=MATRICULE,
    status=UserStatus.ACTIVE.value,
    organisation_id=5,
    platform_role=None,
    created_at=None,
    last_login_at=None,
    updated_at=None,
    deleted_at=None,
    user_projects=[],
)


# -- Route -----------------------------------------------------------------------------


class TestRouteMe:
    @staticmethod
    def _db_avec(user: Any) -> AsyncMock:
        resultat = MagicMock()
        resultat.scalar_one_or_none.return_value = user
        db = AsyncMock()
        db.execute = AsyncMock(return_value=resultat)
        return db

    @staticmethod
    def _overrides(app: FastAPI, db: AsyncMock) -> None:
        app.dependency_overrides[require_user_premiere_connexion] = lambda: UserCaller(
            matricule=MATRICULE, organisation_id=5
        )
        app.dependency_overrides[get_db_premiere_connexion] = lambda: db

    def test_premiere_connexion_projets_vides(self) -> None:
        app = FastAPI()
        app.include_router(me_router)
        self._overrides(app, self._db_avec(USER))
        r = TestClient(app).get("/users/me")

        assert r.status_code == 200, r.text
        assert r.json()["matricule"] == MATRICULE
        assert r.json()["projects"] == []

    def test_montee_avant_users_id_et_sans_get_caller(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dans l'app reelle : « me » n'est pas lu comme un user_id, et get_caller
        (qui refuserait l'agent avant sa creation) n'est pas appele."""
        from adam_api import main  # pylint: disable=import-outside-toplevel

        get_caller = AsyncMock(side_effect=AssertionError("get_caller appele"))
        monkeypatch.setattr(auth_module, "resolve_caller", get_caller)
        self._overrides(main.app, self._db_avec(USER))
        try:
            r = TestClient(main.app).get(f"{main.PREFIX}/users/me")
        finally:
            main.app.dependency_overrides.clear()
        assert r.status_code == 200, r.text

    def test_seule_users_me_cree_des_utilisateurs(self) -> None:
        def appels(dependant: Any) -> List[Any]:
            return [dependant.call] + [c for d in dependant.dependencies for c in appels(d)]

        createurs = []
        for module in pkgutil.iter_modules(routers.__path__):
            contenu = importlib.import_module(f"{routers.__name__}.{module.name}")
            for objet in vars(contenu).values():
                if isinstance(objet, APIRouter):
                    createurs += [
                        route.path
                        for route in objet.routes
                        if isinstance(route, APIRoute)
                        and auth_module.get_caller_premiere_connexion in appels(route.dependant)
                    ]
        assert set(createurs) == {"/users/me"}