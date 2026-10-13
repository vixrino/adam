"""Tests de la recherche dans l'annuaire AD et de l'affectation par matricule.

Aucun AD reel : les filtres et la cadence sont des fonctions pures, le client
ldap3 tourne contre son serveur MOCK_SYNC (si ldap3 est installe), et les
routes recoivent un annuaire factice par surcharge de dependance.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.dependencies.auth import UserCaller, require_user
from adam_api.dependencies.db import get_db
from adam_api.routers import annuaire as annuaire_module
from adam_api.routers.annuaire import get_annuaire, get_limiteur, router
from adam_api.services.annuaire import (
    AnnuaireErreur,
    AnnuaireLdap,
    LimiteurRequetes,
    PersonneAnnuaire,
    dans_ou_exclue,
    echapper,
    filtre_matricule,
    filtre_recherche,
    personne_depuis_attributs,
)

DANIEL = PersonneAnnuaire(
    matricule="I21080M",
    nom_affiche="Daniel Ferreira Lara",
    email="daniel.ferreira@exemple.fr",
    prenom="Daniel",
    nom="Ferreira Lara",
    departement="RE1 US2183 DGSI DIRES SOLAPS",
)


# -- Filtres -----------------------------------------------------------------------


class TestFiltres:
    def test_une_saisie_ne_peut_pas_modifier_le_filtre(self) -> None:
        """`*)(objectClass=*` cherche ces caracteres, il ne rouvre pas le filtre."""
        filtre = filtre_recherche("*)(objectClass=*")
        assert "\\2a\\29\\28objectClass=\\2a" in filtre
        assert echapper("a*b(c)\\") == r"a\2ab\28c\29\5c"

    def test_les_comptes_desactives_sont_exclus(self) -> None:
        for filtre in (filtre_recherche("dan"), filtre_matricule("I21080M")):
            assert "(!(userAccountControl:1.2.840.113556.1.4.803:=2))" in filtre
            assert "(objectCategory=person)" in filtre

    def test_chaque_mot_doit_correspondre(self) -> None:
        filtre = filtre_recherche("Daniel Fer")
        assert filtre.count("(|(sAMAccountName=") == 2
        assert "(sn=Fer*)" in filtre and "(displayName=*Daniel*)" in filtre

    def test_matricule_exact(self) -> None:
        assert "(sAMAccountName=I21080M)" in filtre_matricule(" I21080M ")

    def test_personne_depuis_attributs(self) -> None:
        personne = personne_depuis_attributs(
            {
                "sAMAccountName": "i21080m",
                "givenName": "Daniel",
                "sn": "Ferreira",
                "mail": ["daniel@exemple.fr"],
                "department": "SOLAPS",
                "displayName": [],
            }
        )
        assert personne is not None
        assert personne.nom_affiche == "Daniel Ferreira"
        assert personne.email == "daniel@exemple.fr"
        assert personne_depuis_attributs({"sn": "sans matricule"}) is None


class TestExclusions:
    def test_prefixe_exclu_dans_le_filtre(self) -> None:
        for filtre in (filtre_recherche("dan", ["OT2"]), filtre_matricule("I21080M", ["OT2"])):
            assert "(!(sAMAccountName=OT2*))" in filtre
        assert "(!(" + "sAMAccountName" not in filtre_recherche("dan").replace(
            "(!(userAccountControl", ""
        )

    def test_suffixe_exclu_dans_le_filtre(self) -> None:
        for filtre in (
            filtre_recherche("dan", suffixes_exclus=["OT2"]),
            filtre_matricule("I21080M", suffixes_exclus=["OT2"]),
        ):
            assert "(!(sAMAccountName=*OT2))" in filtre

    def test_prefixe_echappe(self) -> None:
        assert "(!(sAMAccountName=a\\2a*))" in filtre_recherche("dan", ["a*"])

    def test_unite_d_organisation_exclue(self) -> None:
        dn = "CN=Admin,OU=OT2,OU=T2,DC=ADBDFINT,DC=PRIVATE"
        assert dans_ou_exclue(dn, ["ot2"]) is True
        assert dans_ou_exclue("CN=x,OU=OT2BIS,OU=T2,DC=A", ["OT2"]) is False
        assert dans_ou_exclue("CN=x,OU=T2,DC=A", ["OT2"]) is False
        assert dans_ou_exclue(dn, []) is False


class TestLimiteur:
    def test_une_requete_toutes_les_deux_secondes_par_personne(self) -> None:
        limiteur = LimiteurRequetes(2.0)
        assert limiteur.attente("A", maintenant=10.0) == 0
        assert limiteur.attente("A", maintenant=11.0) == pytest.approx(1.0)
        # Une autre personne n'attend pas.
        assert limiteur.attente("B", maintenant=11.0) == 0
        assert limiteur.attente("A", maintenant=12.1) == 0


class TestConfiguration:
    def test_annuaire_incomplet_refuse(self) -> None:
        from adam_api.services.annuaire import AnnuaireDesactive

        with pytest.raises(AnnuaireDesactive, match="AD_PASSWORD"):
            AnnuaireLdap(host="ad", port=636, use_ssl=True, bind_dn="cn=x", password="", base_dn="")


# -- Client ldap3, contre son serveur MOCK ----------------------------------------


class TestAnnuaireLdapMock:
    """Le vrai client, contre le serveur MOCK de ldap3 (ignore sans ldap3)."""

    @pytest.fixture
    def annuaire(self, monkeypatch: pytest.MonkeyPatch) -> AnnuaireLdap:
        ldap3 = pytest.importorskip("ldap3")
        base = "OU=T2,DC=ADBDFINT,DC=PRIVATE"
        bind = "CN=DV_SMARTDOC_SVC,OU=SMARTDOC,DC=ADBDFINT,DC=PRIVATE"
        serveur = ldap3.Server("ad-factice")
        connexion_admin = ldap3.Connection(
            serveur, user=bind, password="secret", client_strategy=ldap3.MOCK_SYNC
        )
        connexion_admin.strategy.add_entry(bind, {"userPassword": "secret", "sn": "svc"})

        def compte(cn: str, matricule: str, actif: bool, **attrs: str) -> None:
            connexion_admin.strategy.add_entry(
                f"CN={cn},{base}",
                {
                    "objectCategory": "person",
                    "objectClass": "user",
                    "sAMAccountName": matricule,
                    "userAccountControl": 512 if actif else 514,
                    **attrs,
                },
            )

        compte(
            "Daniel",
            "I21080M",
            True,
            givenName="Daniel",
            sn="Ferreira",
            displayName="Daniel Ferreira",
            mail="daniel@exemple.fr",
            department="SOLAPS",
        )
        compte("Marie", "V00001", True, givenName="Marie", sn="Kochanowicz", mail="m@exemple.fr")
        connexion_admin.strategy.add_entry(
            f"CN=Daniel Suffixe,{base}",
            {
                "objectCategory": "person",
                "objectClass": "user",
                "sAMAccountName": "I21080MOT2",
                "userAccountControl": 512,
                "givenName": "Daniel",
                "sn": "Suffixe",
            },
        )
        connexion_admin.strategy.add_entry(
            f"CN=Admin Daniel,OU=OT2,{base}",
            {
                "objectCategory": "person",
                "objectClass": "user",
                "sAMAccountName": "OT2I21080M",
                "userAccountControl": 512,
                "givenName": "Daniel",
                "sn": "Admin",
            },
        )

        annuaire = AnnuaireLdap(
            host="ad-factice",
            port=636,
            use_ssl=False,
            bind_dn=bind,
            password="secret",
            base_dn=base,
        )

        def connexion() -> Any:
            # Meme objet Server : ldap3 y range les entrees du MOCK.
            return ldap3.Connection(
                serveur, user=bind, password="secret", client_strategy=ldap3.MOCK_SYNC
            )

        monkeypatch.setattr(annuaire, "_connexion", connexion)
        return annuaire

    @pytest.mark.asyncio
    async def test_recherche_et_lecture_par_matricule(self, annuaire: AnnuaireLdap) -> None:
        trouvees = await annuaire.rechercher("Ferreira")
        assert [p.matricule for p in trouvees] == ["I21080M"]
        assert trouvees[0].departement == "SOLAPS"
        personne = await annuaire.trouver("I21080M")
        assert personne is not None and personne.email == "daniel@exemple.fr"

    @pytest.mark.asyncio
    async def test_comptes_ot2_exclus(self, annuaire: AnnuaireLdap) -> None:
        """Le compte OT2 est sous la base : sans exclusion, il remonte."""
        assert "OT2I21080M" in [p.matricule for p in await annuaire.rechercher("Dan")]
        annuaire.ou_exclues = ["OT2"]
        assert "OT2I21080M" not in [p.matricule for p in await annuaire.rechercher("Dan")]
        annuaire.ou_exclues = []
        annuaire.prefixes_exclus = ["OT2"]
        assert "OT2I21080M" not in [p.matricule for p in await annuaire.rechercher("Dan")]
        assert await annuaire.trouver("OT2I21080M") is None
        # Matricule qui FINIT par OT2 : exclu par suffixe.
        annuaire.prefixes_exclus = []
        assert "I21080MOT2" in [p.matricule for p in await annuaire.rechercher("Dan")]
        annuaire.suffixes_exclus = ["OT2"]
        assert "I21080MOT2" not in [p.matricule for p in await annuaire.rechercher("Dan")]
        assert await annuaire.trouver("I21080MOT2") is None

    @pytest.mark.asyncio
    async def test_matricule_inconnu_rend_none(self, annuaire: AnnuaireLdap) -> None:
        assert await annuaire.trouver("X99999") is None

    # L'exclusion des comptes desactives n'est pas testee ici : le serveur MOCK
    # de ldap3 n'evalue pas la regle bit a bit propre a l'AD
    # (1.2.840.113556.1.4.803) et la laisse passer. TestFiltres verifie qu'elle
    # figure dans chaque filtre ; c'est l'AD qui l'applique.


# -- Routes ---------------------------------------------------------------------------


class _AnnuaireFactice:
    def __init__(self, personnes: List[PersonneAnnuaire], erreur: bool = False) -> None:
        self.personnes = personnes
        self.erreur = erreur
        self.recherches: List[str] = []

    async def rechercher(self, texte: str) -> List[PersonneAnnuaire]:
        if self.erreur:
            raise AnnuaireErreur("injoignable")
        self.recherches.append(texte)
        return self.personnes

    async def trouver(self, matricule: str) -> Optional[PersonneAnnuaire]:
        return next((p for p in self.personnes if p.matricule == matricule.upper()), None)


def _resultat(*, first: Any = None, scalar: Any = None, all_: Any = None) -> MagicMock:
    r = MagicMock()
    r.first.return_value = first
    r.scalar_one_or_none.return_value = scalar
    r.all.return_value = all_ or []
    r.scalars.return_value.all.return_value = all_ or []
    return r


def _client(
    *,
    caller: UserCaller,
    db: AsyncMock,
    annuaire: Any,
    limiteur: Optional[LimiteurRequetes] = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_user] = lambda: caller
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_annuaire] = lambda: annuaire
    app.dependency_overrides[get_limiteur] = lambda: limiteur or LimiteurRequetes(0)
    return TestClient(app)


ADMIN = UserCaller(matricule="V654846", organisation_id=1, platform_role="NOTA_ADMIN")
OPERATEUR = UserCaller(matricule="I659418", organisation_id=1)


def _db(*resultats: MagicMock, project: Any = None, user_project: Any = None) -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    projet = project if project is not None else SimpleNamespace(id=7, organisation_id=1)

    async def get(modele: Any, cle: Any) -> Any:
        return projet if modele.__name__ == "Project" else user_project

    db.get = AsyncMock(side_effect=get)
    db.execute = AsyncMock(side_effect=list(resultats))
    return db


class TestRecherche:
    def test_admin_nota_cherche_et_voit_qui_est_deja_inscrit(self) -> None:
        db = _db(_resultat(all_=[("I21080M", 42)]), _resultat(all_=[42]))
        annuaire = _AnnuaireFactice([DANIEL])
        r = _client(caller=ADMIN, db=db, annuaire=annuaire).get(
            "/annuaire/personnes", params={"project_id": 7, "q": "Dan"}
        )
        assert r.status_code == 200
        corps = r.json()[0]
        assert corps["matricule"] == "I21080M"
        assert corps["departement"] == "RE1 US2183 DGSI DIRES SOLAPS"
        assert corps["deja_inscrite"] is True and corps["deja_membre"] is True

    def test_saisie_trop_courte_refusee_sans_interroger_l_ad(self) -> None:
        annuaire = _AnnuaireFactice([DANIEL])
        r = _client(caller=ADMIN, db=_db(), annuaire=annuaire).get(
            "/annuaire/personnes", params={"project_id": 7, "q": "Da"}
        )
        assert r.status_code == 422
        assert annuaire.recherches == []

    def test_cadence_depassee_429(self) -> None:
        limiteur = LimiteurRequetes(60)
        annuaire = _AnnuaireFactice([])
        client = _client(caller=ADMIN, db=_db(_resultat()), annuaire=annuaire, limiteur=limiteur)
        assert (
            client.get("/annuaire/personnes", params={"project_id": 7, "q": "Dan"}).status_code
            == 200
        )
        r = client.get("/annuaire/personnes", params={"project_id": 7, "q": "Dani"})
        assert r.status_code == 429
        assert int(r.headers["Retry-After"]) >= 1

    def test_operateur_refuse(self) -> None:
        db = _db(_resultat(first=None))
        r = _client(caller=OPERATEUR, db=db, annuaire=_AnnuaireFactice([DANIEL])).get(
            "/annuaire/personnes", params={"project_id": 7, "q": "Dan"}
        )
        assert r.status_code == 403

    def test_admin_metier_du_projet_autorise(self) -> None:
        db = _db(_resultat(first=(1,)), _resultat())
        r = _client(caller=OPERATEUR, db=db, annuaire=_AnnuaireFactice([])).get(
            "/annuaire/personnes", params={"project_id": 7, "q": "Dan"}
        )
        assert r.status_code == 200

    def test_ad_injoignable_502(self) -> None:
        r = _client(caller=ADMIN, db=_db(), annuaire=_AnnuaireFactice([], erreur=True)).get(
            "/annuaire/personnes", params={"project_id": 7, "q": "Dan"}
        )
        assert r.status_code == 502


class TestAffectation:
    def test_personne_jamais_connectee_creee_puis_affectee(self) -> None:
        db = _db(_resultat(scalar=None), _resultat(first=None))

        def add(objet: Any) -> None:
            if objet.__class__.__name__ == "User":
                objet.id = 99

        db.add = MagicMock(side_effect=add)
        r = _client(caller=ADMIN, db=db, annuaire=_AnnuaireFactice([DANIEL])).post(
            "/annuaire/affectations",
            json={"project_id": 7, "matricule": "i21080m", "role": "OPERATOR"},
        )
        assert r.status_code == 201, r.text
        assert r.json() == {
            "user_id": 99,
            "project_id": 7,
            "matricule": "I21080M",
            "role": "OPERATOR",
            "utilisateur_cree": True,
        }
        user = db.add.call_args_list[0].args[0]
        assert user.email == "daniel.ferreira@exemple.fr"
        assert user.full_name == "Daniel Ferreira Lara"
        assert user.organisation_id == 1
        assert user.last_login_at is None

    def test_utilisateur_existant_reutilise(self) -> None:
        existant = SimpleNamespace(id=42, organisation_id=1, matricule="I21080M")
        db = _db(_resultat(scalar=existant))
        r = _client(caller=ADMIN, db=db, annuaire=_AnnuaireFactice([DANIEL])).post(
            "/annuaire/affectations", json={"project_id": 7, "matricule": "I21080M"}
        )
        assert r.status_code == 201
        assert r.json()["utilisateur_cree"] is False
        assert r.json()["user_id"] == 42

    def test_deja_membre_409(self) -> None:
        existant = SimpleNamespace(id=42, organisation_id=1, matricule="I21080M")
        db = _db(_resultat(scalar=existant), user_project=SimpleNamespace(role="OPERATOR"))
        r = _client(caller=ADMIN, db=db, annuaire=_AnnuaireFactice([DANIEL])).post(
            "/annuaire/affectations", json={"project_id": 7, "matricule": "I21080M"}
        )
        assert r.status_code == 409

    def test_autre_organisation_409(self) -> None:
        etranger = SimpleNamespace(id=42, organisation_id=2, matricule="I21080M")
        db = _db(_resultat(scalar=etranger))
        r = _client(caller=ADMIN, db=db, annuaire=_AnnuaireFactice([DANIEL])).post(
            "/annuaire/affectations", json={"project_id": 7, "matricule": "I21080M"}
        )
        assert r.status_code == 409

    def test_matricule_inconnu_ou_desactive_404(self) -> None:
        r = _client(caller=ADMIN, db=_db(), annuaire=_AnnuaireFactice([])).post(
            "/annuaire/affectations", json={"project_id": 7, "matricule": "X00000"}
        )
        assert r.status_code == 404

    def test_compte_sans_mail_422(self) -> None:
        sans_mail = PersonneAnnuaire("V1", "Sans Mail", None, None, None, None)
        db = _db(_resultat(scalar=None))
        r = _client(caller=ADMIN, db=db, annuaire=_AnnuaireFactice([sans_mail])).post(
            "/annuaire/affectations", json={"project_id": 7, "matricule": "V1"}
        )
        assert r.status_code == 422

    def test_annuaire_desactive_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(annuaire_module.settings, "ad_enabled", False)
        with pytest.raises(Exception) as exc:
            get_annuaire()
        assert getattr(exc.value, "status_code", None) == 503
