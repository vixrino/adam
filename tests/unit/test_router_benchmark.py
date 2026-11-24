"""Routes du benchmark OCR (recettes, executions, metriques), base simulee."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from adam_api.core.config import settings
from adam_api.dependencies.auth import UserCaller, require_user
from adam_api.dependencies.db import get_db
from adam_api.routers.benchmark import router

SUPERVISEUR = UserCaller(matricule="V1", organisation_id=1, platform_role="NOTA_SUPERVISOR")
OPERATEUR = UserCaller(matricule="I1", organisation_id=1)
ADMIN = UserCaller(matricule="V2", organisation_id=1, platform_role="NOTA_ADMIN")
_NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


def _resultat(
    *, scalar: Any = None, scalars: Optional[List[Any]] = None, all_: Optional[List[Any]] = None
) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
    r.scalar_one.return_value = scalar
    r.scalars.return_value.all.return_value = scalars or []
    r.all.return_value = all_ or []
    return r


def _client(caller: UserCaller, db: AsyncMock) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_user] = lambda: caller
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _db(objets: Dict[str, Any], *resultats: MagicMock) -> AsyncMock:
    db = AsyncMock()
    ajoutes: List[Any] = []

    def add(objet: Any) -> None:
        objet.id = 50
        objet.created_at = _NOW
        for nom, defaut in (
            ("documents_traites", 0),
            ("documents_compared", 0),
            ("fields_compared", 0),
            ("fields_human_verified", 0),
            ("diff_count", 0),
            ("unexpected_count", 0),
            ("ocr_calls_made", 0),
            ("pages_processed", 0),
        ):
            if hasattr(type(objet), nom) and getattr(objet, nom) is None:
                setattr(objet, nom, defaut)
        ajoutes.append(objet)

    db.add = MagicMock(side_effect=add)
    db.ajoutes = ajoutes
    db.get = AsyncMock(side_effect=lambda modele, cle: objets.get(modele.__name__))
    db.execute = AsyncMock(side_effect=list(resultats))
    return db


def _recette(status: str = "LOCKED", config: Optional[Dict[str, Any]] = None, **autres: Any) -> Any:
    base = dict(
        id=3,
        dataset_id=4,
        dataset_export_id=8,
        tout_l_export=False,
        version=1,
        recette_racine_id=None,
        name="r",
        description=None,
        document_ids=[14],
        status=status,
        config=config or {},
        locked_at=_NOW,
        created_at=_NOW,
    )

    return SimpleNamespace(**{**base, **autres})


def _export(documents: Optional[List[int]] = None) -> Any:
    return SimpleNamespace(
        id=8,
        dataset_id=4,
        schema_id=9,
        schema_hash="abcd",
        name="novembre",
        description=None,
        document_ids=documents or [14, 15],
        created_at=_NOW,
    )


def _execution(status: str = "COMPLETED") -> Any:
    return SimpleNamespace(
        id=1,
        recipe_id=3,
        status=status,
        ocr_provider="mistral",
        ocr_model_id="ocr + annot",
        comparateur_version="1",
        schema_hash="abc",
        verite_hash="v1",
        error_message=None,
        documents_traites=1,
        documents_compared=1,
        fields_compared=41,
        fields_human_verified=41,
        diff_count=2,
        unexpected_count=0,
        ocr_calls_made=35,
        pages_processed=12,
        created_at=_NOW,
        started_at=_NOW,
        finished_at=_NOW,
        created_by_user_id=1,
        updated_at=_NOW,
        confidence_histogram=None,
    )


def _rapports(rapports: List[Any], libelle: Optional[str] = None) -> MagicMock:
    """Resultat de la requete des rapports : (rapport, libelle de section)."""
    return _resultat(all_=[(r, libelle) for r in rapports])


def _rapport(field_key: str, **comptes: Any) -> Any:
    base = dict(
        id=1,
        execution_id=1,
        field_spec_id=1,
        field_key=field_key,
        compared=1,
        diff_count=0,
        vp=0,
        fp=0,
        fn=0,
        vn=0,
        substitutions=0,
        somme_distance=0,
        somme_longueur_attendue=0,
        page=1,
        section_id=field_key.split(".")[0],
        value_type="TEXT",
        sensitive=False,
    )
    return SimpleNamespace(**{**base, **comptes})


class TestDroits:
    def test_operateur_refuse(self) -> None:
        r = _client(OPERATEUR, _db({})).get("/test-recipes")
        assert r.status_code == 403


class TestExports:
    def test_creation_sur_les_documents_verifies(self) -> None:
        db = _db(
            {"Dataset": SimpleNamespace(id=4, schema_id=9)},
            _resultat(scalars=[14, 15]),  # documents avec proposition humaine
            _resultat(scalar=None),  # nom d'export libre
            _resultat(scalar="CERFA"),  # schema : nom
            _resultat(all_=[(1, "Deposant")]),  # schema : pages
            _resultat(scalars=[]),  # schema : champs
            _resultat(all_=[(14, 1, None, "DUPONT")]),  # verite : champs verifies
            _resultat(scalar=1),  # createur
        )
        r = _client(SUPERVISEUR, db).post(
            "/dataset-exports", json={"dataset_id": 4, "name": "novembre"}
        )
        assert r.status_code == 201, r.text
        corps = r.json()
        assert corps["document_ids"] == [14, 15] and corps["schema_id"] == 9
        assert len(corps["schema_hash"]) == 16
        # Une empreinte par document, meme sans champ verifie (le 15).
        empreintes = db.ajoutes[0].verite_empreintes
        assert set(empreintes) == {"14", "15"} and empreintes["14"] != empreintes["15"]


    def test_document_hors_du_dataset_422(self) -> None:
        db = _db({"Dataset": SimpleNamespace(id=4, schema_id=9)}, _resultat(scalars=[14]))
        r = _client(SUPERVISEUR, db).post(
            "/dataset-exports", json={"dataset_id": 4, "name": "x", "document_ids": [14, 99]}
        )
        assert r.status_code == 422 and "99" in r.text

    def test_sans_verite_terrain_422(self) -> None:
        db = _db({"Dataset": SimpleNamespace(id=4, schema_id=9)}, _resultat(scalars=[]))
        r = _client(SUPERVISEUR, db).post("/dataset-exports", json={"dataset_id": 4, "name": "x"})
        assert r.status_code == 422

    def test_reserve_au_benchmark(self) -> None:
        db = _db({"Dataset": SimpleNamespace(id=4, schema_id=9)})
        r = _client(OPERATEUR, db).post("/dataset-exports", json={"dataset_id": 4, "name": "x"})
        assert r.status_code == 403


class TestRecettes:
    def _creer(
        self, corps: Dict[str, Any], *resultats: MagicMock, caller: UserCaller = ADMIN
    ) -> Any:
        db = _db({"DatasetExport": _export()}, *resultats)
        return _client(caller, db).post("/test-recipes", json=corps)

    def test_consigne_reservee_aux_administrateurs(self) -> None:
        corps = {
            "dataset_export_id": 8,
            "name": "c",
            "tout_l_export": True,
            "config": {"ocr": {"prompt": "Lis."}},
        }
        r = self._creer(corps, caller=SUPERVISEUR)
        assert r.status_code == 403 and "administrateurs" in r.text

    def test_superviseur_sans_consigne_accepte(self) -> None:
        r = self._creer(
            {"dataset_export_id": 8, "name": "c", "tout_l_export": True},
            _resultat(scalar=None),
            _resultat(scalar=1),
            caller=SUPERVISEUR,
        )
        assert r.status_code == 201, r.text

    def test_consigne_refusee_au_superviseur_en_patch_et_en_version(self) -> None:
        db = _db({"TestRecipe": _recette("DRAFT")})
        corps = {"config": {"ocr": {"prompt": "Lis."}}}
        client = _client(SUPERVISEUR, db)
        assert client.patch("/test-recipes/3", json=corps).status_code == 403
        assert client.post("/test-recipes/3/versions", json=corps).status_code == 403


    def test_creation_sur_tout_l_export_avec_moteur(self) -> None:
        r = self._creer(
            {
                "dataset_export_id": 8,
                "name": "cerfa",
                "tout_l_export": True,
                "config": {
                    "score_minimal": 0.9,
                    "seuils_par_categorie": {"sensible": 0.0},
                    "ocr": {"provider": "mistral", "model": "mistral-ocr-2", "prompt": "Lis."},
                },
            },
            _resultat(scalar=None),  # nom libre
            _resultat(scalar=1),  # createur
        )
        assert r.status_code == 201, r.text
        corps = r.json()
        assert corps["status"] == "DRAFT" and corps["document_ids"] == [14, 15]
        assert (corps["dataset_export_id"], corps["dataset_id"], corps["version"]) == (8, 4, 1)
        assert corps["config"]["ocr"] == {
            "provider": "MISTRAL",
            "model": "mistral-ocr-2",
            "annotation_model": settings.mistral_annotation_model,
            "prompt": "Lis.",
        }
        assert corps["config"]["seuils_par_categorie"] == {"sensible": 0.0}

    def test_liste_prise_dans_l_export(self) -> None:
        r = self._creer(
            {"dataset_export_id": 8, "name": "c", "document_ids": [15]},
            _resultat(scalar=None),
            _resultat(scalar=1),
        )
        assert r.status_code == 201, r.text
        assert r.json()["document_ids"] == [15] and r.json()["tout_l_export"] is False

    def test_document_hors_export_422(self) -> None:
        r = self._creer({"dataset_export_id": 8, "name": "c", "document_ids": [14, 99]})
        assert r.status_code == 422 and "99" in r.text

    def test_ni_liste_ni_tout_l_export_422(self) -> None:
        assert self._creer({"dataset_export_id": 8, "name": "c"}).status_code == 422

    def test_liste_et_tout_l_export_422(self) -> None:
        corps = {"dataset_export_id": 8, "name": "c", "tout_l_export": True, "document_ids": [14]}
        assert self._creer(corps).status_code == 422

    def test_fournisseur_inconnu_422(self) -> None:
        corps = {
            "dataset_export_id": 8,
            "name": "c",
            "tout_l_export": True,
            "config": {"ocr": {"provider": "PULSAR"}},
        }
        assert self._creer(corps).status_code == 422

    def test_seuil_hors_bornes_422(self) -> None:
        corps = {
            "dataset_export_id": 8,
            "name": "c",
            "tout_l_export": True,
            "config": {"seuils_par_categorie": {"sensible": 2}},
        }
        assert self._creer(corps).status_code == 422

    def test_nom_deja_pris_409(self) -> None:
        r = self._creer(
            {"dataset_export_id": 8, "name": "c", "tout_l_export": True}, _resultat(scalar=3)
        )
        assert r.status_code == 409 and "/test-recipes/3/versions" in r.text

    def test_export_inconnu_404(self) -> None:
        db = _db({})
        r = _client(SUPERVISEUR, db).post(
            "/test-recipes", json={"dataset_export_id": 8, "name": "c", "tout_l_export": True}
        )
        assert r.status_code == 404


    def test_recette_figee_non_modifiable(self) -> None:
        db = _db({"TestRecipe": _recette("LOCKED")})

        r = _client(SUPERVISEUR, db).patch("/test-recipes/3", json={"description": "autre"})
        assert r.status_code == 409 and "/versions" in r.text

class TestRefus:
    """Ce que la relecture a releve : recettes sans export, doublons, null."""

    def test_nom_d_export_deja_pris_409(self) -> None:
        db = _db(
            {"Dataset": SimpleNamespace(id=4, schema_id=9)},
            _resultat(scalars=[14]),
            _resultat(scalar=2),  # nom deja pris
        )
        r = _client(SUPERVISEUR, db).post(
            "/dataset-exports", json={"dataset_id": 4, "name": "novembre"}
        )
        assert r.status_code == 409 and "id 2" in r.text

    def test_conflit_a_l_ecriture_409_et_non_500(self) -> None:
        from sqlalchemy.exc import IntegrityError

        db = _db({"DatasetExport": _export()}, _resultat(scalar=None), _resultat(scalar=1))
        db.flush = AsyncMock(side_effect=IntegrityError("insert", {}, Exception("unique")))
        r = _client(SUPERVISEUR, db).post(
            "/test-recipes", json={"dataset_export_id": 8, "name": "c", "tout_l_export": True}
        )
        assert r.status_code == 409

    def test_recette_sans_export_ni_version_ni_patch_ni_execution(self) -> None:
        ancienne = _recette("LOCKED", dataset_export_id=None)
        brouillon = _recette("DRAFT", dataset_export_id=None)
        client = _client(SUPERVISEUR, _db({"TestRecipe": ancienne}))
        assert client.post("/test-recipes/3/versions", json={}).status_code == 409
        assert client.post("/test-executions", json={"recipe_id": 3}).status_code == 409
        client = _client(SUPERVISEUR, _db({"TestRecipe": brouillon}))
        r = client.patch("/test-recipes/3", json={"document_ids": [999]})
        assert r.status_code == 409 and "/dataset-exports" in r.text

    def test_version_d_un_brouillon_409(self) -> None:
        db = _db({"TestRecipe": _recette("DRAFT")})
        r = _client(SUPERVISEUR, db).post("/test-recipes/3/versions", json={})
        assert r.status_code == 409 and "PATCH" in r.text

    def test_version_d_une_version_ancienne_409(self) -> None:
        v1 = _recette("LOCKED")
        v2 = _recette("LOCKED", id=5, version=2, recette_racine_id=3)
        db = _db({"TestRecipe": v1}, _resultat(scalars=[v1, v2]))
        r = _client(SUPERVISEUR, db).post("/test-recipes/3/versions", json={})
        assert r.status_code == 409 and "/test-recipes/5/versions" in r.text

    def test_null_refuse(self) -> None:
        db = _db({"TestRecipe": _recette("DRAFT")})
        r = _client(SUPERVISEUR, db).patch("/test-recipes/3", json={"tout_l_export": None})
        assert r.status_code == 422

    def test_patch_tout_l_export_faux_garde_la_liste(self) -> None:
        db = _db(
            {
                "TestRecipe": _recette("DRAFT", tout_l_export=True, document_ids=[14, 15]),
                "DatasetExport": _export(),
            }
        )
        r = _client(SUPERVISEUR, db).patch("/test-recipes/3", json={"tout_l_export": False})
        assert r.status_code == 200, r.text
        assert r.json()["document_ids"] == [14, 15] and r.json()["tout_l_export"] is False

    def test_consigne_trop_longue_et_modele_vide(self) -> None:
        from adam_core.benchmark.recette import CONSIGNE_MAX, ConfigOcr

        corps = {
            "dataset_export_id": 8,
            "name": "c",
            "tout_l_export": True,
            "config": {"ocr": {"prompt": "x" * (CONSIGNE_MAX + 1)}},
        }
        db = _db({"DatasetExport": _export()})
        assert _client(SUPERVISEUR, db).post("/test-recipes", json=corps).status_code == 422
        assert ConfigOcr(model="  ", prompt="").model is None
        assert ConfigOcr(model=" ocr-2 ").model == "ocr-2"

    def test_execution_provisoire_avec_le_moteur_de_la_recette(self) -> None:
        recette = _recette("LOCKED", config={"ocr": {"provider": "MISTRAL", "model": "ocr-2"}})
        db = _db({"TestRecipe": recette}, _resultat(scalar=1))
        r = _client(SUPERVISEUR, db).post("/test-executions", json={"recipe_id": 3})
        assert r.status_code == 201, r.text
        assert (r.json()["ocr_provider"], r.json()["ocr_model_id"]) == ("MISTRAL", "ocr-2")


class TestVersions:
    def test_nouvelle_version_avec_un_autre_moteur(self) -> None:
        source = _recette("LOCKED", config={"score_minimal": 0.8})
        db = _db(
            {"TestRecipe": source, "DatasetExport": _export()},
            _resultat(scalars=[source]),  # famille
            _resultat(scalar=1),  # createur
        )
        r = _client(SUPERVISEUR, db).post(
            "/test-recipes/3/versions",
            json={
                "document_ids": [14, 15],
                "config": {"score_minimal": 0.8, "ocr": {"model": "mistral-ocr-2"}},
            },
        )
        assert r.status_code == 201, r.text
        corps = r.json()
        assert (corps["name"], corps["version"], corps["recette_racine_id"]) == ("r", 2, 3)
        assert corps["document_ids"] == [14, 15] and corps["status"] == "DRAFT"
        assert corps["config"]["ocr"]["model"] == "mistral-ocr-2"
        assert corps["config"]["ocr"]["provider"] in ("MISTRAL", "MOCK", "SMARTDOC_JSON")
        assert source.version == 1 and source.document_ids == [14]  # la source ne bouge pas

    def test_sans_corps_reprend_la_source(self) -> None:
        source = _recette("LOCKED", config={"score_minimal": 0.8})
        v2 = _recette("LOCKED", id=5, version=2, recette_racine_id=3)
        db = _db(
            {"TestRecipe": v2, "DatasetExport": _export()},
            _resultat(scalars=[source, v2]),
            _resultat(scalar=1),
        )
        r = _client(SUPERVISEUR, db).post("/test-recipes/5/versions", json={})
        assert r.status_code == 201, r.text
        corps = r.json()
        assert (corps["version"], corps["recette_racine_id"]) == (3, 3)
        assert corps["document_ids"] == [14]


    def test_config_partielle_fusionnee_avec_la_source(self) -> None:
        """Le corps dit ce qui change : le reste de la config est garde."""
        source = _recette(
            "LOCKED",
            config={
                "champs_exclus": ["certification."],
                "seuils_par_categorie": {"sensible": 0.0},
                "ocr": {"provider": "MISTRAL", "model": "ocr-fige", "prompt": "lire"},
            },
        )
        db = _db(
            {"TestRecipe": source, "DatasetExport": _export()},
            _resultat(scalars=[source]),
            _resultat(scalar=1),
        )
        r = _client(SUPERVISEUR, db).post(
            "/test-recipes/3/versions", json={"config": {"score_minimal": 0.9}}
        )
        assert r.status_code == 201, r.text
        config = r.json()["config"]
        assert config["score_minimal"] == 0.9
        assert config["champs_exclus"] == ["certification."]
        assert config["seuils_par_categorie"] == {"sensible": 0.0}
        assert config["ocr"]["model"] == "ocr-fige" and config["ocr"]["prompt"] == "lire"

    def test_autre_fournisseur_repart_d_un_moteur_vide(self) -> None:
        brouillon = _recette(
            "DRAFT", config={"ocr": {"provider": "MISTRAL", "model": "ocr-fige", "prompt": "x"}}
        )
        db = _db({"TestRecipe": brouillon})
        r = _client(ADMIN, db).patch(
            "/test-recipes/3", json={"config": {"ocr": {"provider": "MOCK"}}}
        )
        assert r.status_code == 200, r.text
        assert r.json()["config"]["ocr"] == {"provider": "MOCK"}

    def test_patch_liste_seule_quitte_tout_l_export(self) -> None:
        db = _db(
            {
                "TestRecipe": _recette("DRAFT", tout_l_export=True, document_ids=[14, 15]),
                "DatasetExport": _export(),
            }
        )
        r = _client(SUPERVISEUR, db).patch("/test-recipes/3", json={"document_ids": [14]})
        assert r.status_code == 200, r.text
        assert r.json()["document_ids"] == [14] and r.json()["tout_l_export"] is False


    def test_lister_les_versions(self) -> None:
        source = _recette("LOCKED")
        v2 = _recette("LOCKED", id=5, version=2, recette_racine_id=3)
        db = _db({"TestRecipe": v2}, _resultat(scalars=[source, v2]))
        r = _client(SUPERVISEUR, db).get("/test-recipes/5/versions")
        assert r.status_code == 200, r.text
        assert [v["version"] for v in r.json()] == [1, 2]


class TestExecutions:
    def test_lancement(self) -> None:
        db = _db(
            {
                "TestRecipe": _recette(),
                "Dataset": SimpleNamespace(ocr_provider="mistral", ocr_model_id=None),
            },
            _resultat(scalar=1),
        )
        r = _client(SUPERVISEUR, db).post("/test-executions", json={"recipe_id": 3})
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "PENDING"

    def test_lancer_un_brouillon_le_fige(self) -> None:
        recette = _recette("DRAFT", locked_at=None)
        db = _db({"TestRecipe": recette}, _resultat(scalar=1))
        r = _client(SUPERVISEUR, db).post("/test-executions", json={"recipe_id": 3})
        assert r.status_code == 201, r.text
        assert recette.status == "LOCKED" and recette.locked_at is not None

    def test_brouillon_sans_document_non_lance(self) -> None:
        recette = _recette("DRAFT", document_ids=[])
        db = _db({"TestRecipe": recette})
        r = _client(SUPERVISEUR, db).post("/test-executions", json={"recipe_id": 3})
        assert r.status_code == 422 and recette.status == "DRAFT"

    def test_recette_archivee_non_lancee(self) -> None:
        db = _db({"TestRecipe": _recette("ARCHIVED")})
        r = _client(SUPERVISEUR, db).post("/test-executions", json={"recipe_id": 3})
        assert r.status_code == 409

    def test_archiver(self) -> None:
        for avant in ("DRAFT", "LOCKED"):
            recette = _recette(avant)
            r = _client(SUPERVISEUR, _db({"TestRecipe": recette})).post("/test-recipes/3/archive")
            assert r.status_code == 200 and r.json()["status"] == "ARCHIVED"

    def test_archiver_deux_fois_409(self) -> None:
        db = _db({"TestRecipe": _recette("ARCHIVED")})
        assert _client(SUPERVISEUR, db).post("/test-recipes/3/archive").status_code == 409

    def test_metriques_avant_la_fin_409(self) -> None:
        db = _db({"TestExecution": _execution("RUNNING")})
        r = _client(SUPERVISEUR, db).get("/test-executions/1/metriques")
        assert r.status_code == 409

    def test_metriques(self) -> None:
        db = _db(
            # seuil_f1 : l'ancien nom, encore lu pour les recettes deja figees.
            {"TestExecution": _execution(), "TestRecipe": _recette(config={"seuil_f1": 0.5})},
            _rapports(
                [
                    _rapport("deposant.nom", vp=8, fn=2),
                    _rapport("deposant.prenoms", vp=1, fp=1, fn=1, substitutions=1),
                ]
            ),
            _resultat(all_=[("DIGIT", "WRONG", 1), (None, "MISSING", 2)]),
        )
        r = _client(SUPERVISEUR, db).get("/test-executions/1/metriques")
        assert r.status_code == 200, r.text
        m = r.json()
        assert m["global"]["justes"] == 9
        assert m["global"]["fausses"] == 1
        assert m["global"]["taux_valeurs_trouvees"] == round(9 / 12, 4)
        # Les deux champs sont en erreur : aucun n'est filtre.
        assert len(m["par_champ"]) == 2 and m["champs_sans_erreur"] == 0
        assert m["categories_erreurs"] == {"DIGIT": 1, "MISSING": 2}
        assert m["verdict"]["reussi"] is True
        assert m["execution"]["schema_hash"] == "abc"

    def test_progression_en_cours(self) -> None:
        execution = _execution("RUNNING")
        execution.started_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        execution.finished_at = None
        db = _db({"TestExecution": execution, "TestRecipe": _recette(document_ids=[1, 2, 3, 4])})
        r = _client(SUPERVISEUR, db).get("/test-executions/1/progression")
        assert r.status_code == 200, r.text
        p = r.json()
        assert (p["documents_traites"], p["documents_total"], p["pourcentage"]) == (1, 4, 25.0)
        assert p["termine"] is False and p["annulable"] is True
        # 1 document en ~60 s, 3 restants : ~180 s.
        assert 170 < p["secondes_restantes_estimees"] < 200

    def test_progression_terminee_a_100(self) -> None:
        db = _db({"TestExecution": _execution(), "TestRecipe": _recette(document_ids=[1, 2])})
        p = _client(SUPERVISEUR, db).get("/test-executions/1/progression").json()
        assert p["pourcentage"] == 100.0 and p["termine"] is True
        assert p["annulable"] is False and p["secondes_restantes_estimees"] is None

    def test_progression_execution_inconnue_404(self) -> None:
        r = _client(SUPERVISEUR, _db({})).get("/test-executions/9/progression")
        assert r.status_code == 404

    def test_annulation(self) -> None:
        execution = _execution("RUNNING")
        db = _db({"TestExecution": execution}, _resultat(scalar=1))
        r = _client(SUPERVISEUR, db).post("/test-executions/1/cancel")
        assert r.status_code == 200, r.text
        sql = str(db.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
        # Conditionnelle : un passage termine entre-temps n'est pas ecrase.
        assert "test_execution.status IN" in sql and "RETURNING" in sql

    def test_annulation_d_un_passage_termine_409(self) -> None:
        db = _db({"TestExecution": _execution("COMPLETED")}, _resultat(scalar=None))
        r = _client(SUPERVISEUR, db).post("/test-executions/1/cancel")
        assert r.status_code == 409 and "COMPLETED" in r.text

    def test_annulation_execution_inconnue_404(self) -> None:
        db = _db({}, _resultat(scalar=None))
        assert _client(SUPERVISEUR, db).post("/test-executions/9/cancel").status_code == 404

    def test_annulation_reservee_au_benchmark(self) -> None:
        r = _client(OPERATEUR, _db({})).post("/test-executions/1/cancel")
        assert r.status_code == 403



    def test_executions_de_l_export(self) -> None:
        db = _db(
            {"DatasetExport": _export(), "TestExecution": _execution(), "TestRecipe": _recette()},
            _resultat(scalars=[1]),  # executions terminees de l'export
            _rapports([_rapport("a.b", vp=4, fn=1)]),
            _resultat(),  # categories d'erreurs
        )
        r = _client(SUPERVISEUR, db).get("/dataset-exports/8/executions")
        assert r.status_code == 200, r.text
        (ligne,) = r.json()
        assert ligne["execution_id"] == 1 and ligne["recette"]["dataset_export_id"] == 8
        assert ligne["ocr_model_id"] == "ocr + annot"
        assert ligne["taux_valeurs_trouvees"] == 0.8

    def test_executions_d_un_export_inconnu_404(self) -> None:
        r = _client(SUPERVISEUR, _db({})).get("/dataset-exports/99/executions")
        assert r.status_code == 404


    def test_comparaison_n_est_pas_prise_pour_un_id(self) -> None:
        execution = _execution()
        db = _db(
            {"TestExecution": execution, "TestRecipe": _recette()},
            _rapports([_rapport("a.b", vp=5)]),
            _resultat(),
            _rapports([_rapport("a.b", vp=4, fn=1)]),
            _resultat(),
        )
        r = _client(SUPERVISEUR, db).get("/test-executions/comparaison", params={"a": 1, "b": 1})
        assert r.status_code == 200, r.text
        assert r.json()["comparable"] is True
        assert r.json()["global"]["taux_valeurs_trouvees"]["evolution"] == -0.2

    def test_ecarts(self) -> None:
        cr = SimpleNamespace(
            verdict="WRONG",
            diff_kind="DIGIT",
            expected_value=None,
            observed_value=None,
            edit_distance=1,
        )
        df = SimpleNamespace(document_id=14, group_id=None)
        fs = SimpleNamespace(section_id="gestion_budget", field_key="iban", page=4, sensitive=True)
        db = _db(
            {"TestExecution": _execution()},
            _resultat(scalar=1),  # le compte, pour X-Total-Count
            _resultat(all_=[(cr, df, fs, "fausse")]),
        )
        r = _client(SUPERVISEUR, db).get("/test-executions/1/ecarts")
        assert r.status_code == 200, r.text
        assert r.headers["X-Total-Count"] == "1"
        ecart = r.json()[0]
        assert ecart["field_key"] == "gestion_budget.iban"
        assert ecart["champ"] == "gestion_budget.iban" and ecart["type_erreur"] == "fausse"
        assert ecart["sensitive"] is True and ecart["expected_value"] is None

    def test_ecarts_d_une_ligne_de_tableau(self) -> None:
        cr = SimpleNamespace(
            verdict="WRONG",
            diff_kind="TOTAL",
            expected_value=None,
            observed_value="SOFINCO",
            edit_distance=7,
        )
        df = SimpleNamespace(document_id=14, group_id="pret_7")
        fs = SimpleNamespace(
            section_id="credits_consommation", field_key="nom_creancier", page=11, sensitive=False
        )
        db = _db(
            {"TestExecution": _execution()},
            _resultat(scalar=7),
            _resultat(all_=[(cr, df, fs, "inventee")]),
        )
        r = _client(SUPERVISEUR, db).get(
            "/test-executions/1/ecarts",
            params={
                "champ": "credits_consommation.nom_creancier[pret_7]",
                "type_erreur": "inventee",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()[0]["champ"] == "credits_consommation.nom_creancier[pret_7]"
        assert r.json()[0]["type_erreur"] == "inventee"
        assert r.headers["X-Total-Count"] == "7"  # toutes pages confondues

    def test_ecarts_champ_illisible_422(self) -> None:
        db = _db({"TestExecution": _execution()})
        r = _client(SUPERVISEUR, db).get("/test-executions/1/ecarts", params={"champ": "a[b"})
        assert r.status_code == 422

    def test_type_d_erreur_inconnu_422(self) -> None:
        db = _db({"TestExecution": _execution()})
        for route in ("/test-executions/1/ecarts", "/test-executions/1/metriques"):
            r = _client(SUPERVISEUR, db).get(route, params={"type_erreur": "oubliee"})
            assert r.status_code == 422, route

    def test_metriques_filtrees(self) -> None:
        db = _db(
            {"TestExecution": _execution(), "TestRecipe": _recette()},
            _rapports(
                [
                    _rapport("deposant.nom", vp=8, fn=2),
                    _rapport("credits.montant", vp=1, fp=3, value_type="NUMBER"),
                ]
            ),
            _resultat(),
        )
        r = _client(SUPERVISEUR, db).get(
            "/test-executions/1/metriques",
            params=[
                ("type_champ", "NUMBER"),
                ("type_champ", "DATE"),
                ("reussite_inferieure_a", "0.5"),
                ("recherche", "  "),
            ],
        )
        assert r.status_code == 200, r.text
        m = r.json()
        assert [c["champ"] for c in m["par_champ"]] == ["credits.montant"]
        assert m["par_champ"][0]["echec_principal"] == "inventee"
        assert m["selection"] == {
            "filtres": {"types_champ": ["NUMBER", "DATE"], "reussite_inferieure_a": 0.5},
            "champs": 1,
            "champs_verifies": 2,
        }
        assert m["global"]["justes"] == 9  # le score reste celui de tout le test
        assert m["recette"] == {
            "id": 3,
            "name": "r",
            "version": 1,
            "dataset_export_id": 8,
            "document_ids": [14],
            "champs_exclus": [],
        }
        assert m["dataset"]["id"] == 4

class TestRapportPdf:
    def test_pdf_avec_filtres(self) -> None:
        cr = SimpleNamespace(
            verdict="WRONG",
            diff_kind="TOTAL",
            expected_value=None,
            observed_value="Sofinco",
            edit_distance=7,
        )
        df = SimpleNamespace(document_id=14, group_id=None)
        fs = SimpleNamespace(section_id="credits", field_key="montant", page=10, sensitive=False)
        db = _db(
            {
                "TestExecution": _execution(),
                "TestRecipe": _recette(),
                "Dataset": SimpleNamespace(name="cerfa"),
            },
            _rapports(
                [
                    _rapport("deposant.nom", vp=8, fn=2),
                    _rapport("credits.montant", vp=1, fp=3, value_type="NUMBER"),
                ]
            ),
            _resultat(),
            _resultat(all_=[(cr, df, fs, "inventee")]),
        )
        r = _client(SUPERVISEUR, db).get(
            "/test-executions/1/metriques.pdf", params={"type_champ": "NUMBER"}
        )
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert 'filename="rapport-test-1.pdf"' in r.headers["content-disposition"]
        assert r.content.startswith(b"%PDF-")
        # Un seul champ retenu : une seule requete d'extraits.
        assert db.execute.await_count == 3

    def test_pdf_avant_la_fin_409(self) -> None:
        db = _db({"TestExecution": _execution("RUNNING")})
        r = _client(SUPERVISEUR, db).get("/test-executions/1/metriques.pdf")
        assert r.status_code == 409

    def test_pdf_reserve_au_benchmark(self) -> None:
        db = _db({"TestExecution": _execution()})
        r = _client(OPERATEUR, db).get("/test-executions/1/metriques.pdf")
        assert r.status_code == 403

_SMARTDOC = {"ocr": {"provider": "SMARTDOC_JSON"}}


def _json_smartdoc(nom: str = "doc") -> bytes:
    return (
        '{"smartdoc_version":"0.3","document_id":"%s","page_count":1,'
        '"pages":[],"metadata":{"provider":"smartdoc"}}' % nom
    ).encode()


class TestSmartdocJson:
    def _lancer(self, db: AsyncMock, fichiers: List[Any], libelle: str = "v2.3") -> Any:
        return _client(SUPERVISEUR, db).post(
            "/test-executions/smartdoc-json",
            data={"recipe_id": "3", "libelle": libelle},
            files=fichiers,
        )

    def _db(self, config: Dict[str, Any]) -> AsyncMock:
        return _db(
            {"TestRecipe": _recette("DRAFT", config=config, locked_at=None)},
            _resultat(scalars=["Doc1.pdf", "autre.pdf"]),
            _resultat(scalar=1),
        )

    def test_depot_relie_au_nom_garde_les_json_et_fige_la_recette(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        monkeypatch.setattr(settings, "pvc_mount_path", str(tmp_path))
        db = self._db(_SMARTDOC)
        r = self._lancer(db, [("fichiers", ("doc1.json", _json_smartdoc(), "application/json"))])
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "PENDING" and r.json()["ocr_provider"] == "SMARTDOC_JSON"
        assert r.json()["ocr_model_id"] == "v2.3"
        dossier = tmp_path / "benchmark" / "smartdoc_json" / "50"
        assert (dossier / "Doc1.json").is_file()  # nomme comme le document
        assert "v2.3" in (dossier / "_meta.json").read_text()

    def test_json_sans_document_et_json_illisible_refuses(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        monkeypatch.setattr(settings, "pvc_mount_path", str(tmp_path))
        r = self._lancer(
            self._db(_SMARTDOC),
            [
                ("fichiers", ("inconnu.json", _json_smartdoc(), "application/json")),
                ("fichiers", ("doc1.json", b'{"x": 1}', "application/json")),
                ("fichiers", ("autre.txt", b"x", "text/plain")),
            ],
        )
        assert r.status_code == 422
        detail = " ".join(r.json()["detail"])
        assert "inconnu.json : aucun document" in detail
        assert "doc1.json : JSON non conforme" in detail
        assert "autre.txt : extension .json" in detail
        assert not (tmp_path / "benchmark").exists()  # rien d'ecrit

    def test_recette_d_un_autre_moteur_refusee(self) -> None:
        r = self._lancer(
            self._db({"ocr": {"provider": "MISTRAL"}}),
            [("fichiers", ("doc1.json", _json_smartdoc(), "application/json"))],
        )
        assert r.status_code == 409

    def test_le_lancement_simple_renvoie_au_depot_de_json(self) -> None:
        db = _db({"TestRecipe": _recette("LOCKED", config=_SMARTDOC)})
        r = _client(SUPERVISEUR, db).post("/test-executions", json={"recipe_id": 3})
        assert r.status_code == 409 and "smartdoc-json" in r.text


class TestArchiveExport:
    def test_zip_avec_pdf_labellisation_et_manifest(self, tmp_path: Any, monkeypatch: Any) -> None:
        import io
        import json
        import zipfile

        monkeypatch.setattr(settings, "pvc_mount_path", str(tmp_path))
        (tmp_path / "f").mkdir()
        (tmp_path / "f" / "a.pdf").write_bytes(b"%PDF-1.4 a")
        documents = [
            (
                SimpleNamespace(id=14, file_name="Dossier A.pdf"),
                SimpleNamespace(file_path="f/a.pdf", page_count=1),
            ),
            (  # meme nom, fichier absent du PVC
                SimpleNamespace(id=15, file_name="dossier a.pdf"),
                SimpleNamespace(file_path="f/absent.pdf", page_count=1),
            ),
        ]
        champ = (
            SimpleNamespace(group_id=None, resolved_value="Jean"),
            SimpleNamespace(
                page=1,
                section_id="dep",
                section_label="Dep",
                field_key="dep.nom",
                display_label="Nom",
                value_type="TEXT",
                polygon=None,
            ),
            True,
        )
        db = _db(
            {"DatasetExport": _export()},
            _resultat(all_=documents),
            _resultat(all_=[champ]),
            _resultat(all_=[champ]),
        )
        r = _client(SUPERVISEUR, db).get("/dataset-exports/8/archive")
        assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
        archive = zipfile.ZipFile(io.BytesIO(r.content))
        assert sorted(archive.namelist()) == ["Dossier A.json", "Dossier A.pdf", "manifest.json"]
        assert archive.read("Dossier A.pdf") == b"%PDF-1.4 a"
        labellisation = json.loads(archive.read("Dossier A.json"))
        assert labellisation["pages"][0]["sections"][0]["kv_pairs"][0]["value"]["text"] == "Jean"
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["export"]["id"] == 8 and manifest["documents_absents_du_pvc"] == [15]
        assert manifest["documents"][0]["champs_verifies"] == 1

    def test_reserve_aux_superviseurs(self) -> None:
        r = _client(OPERATEUR, _db({})).get("/dataset-exports/8/archive")
        assert r.status_code == 403

    def test_option_sans_sensibles_vide_les_valeurs_des_champs_sensibles(
        self, tmp_path: Any, monkeypatch: Any
    ) -> None:
        import io
        import json
        import zipfile

        monkeypatch.setattr(settings, "pvc_mount_path", str(tmp_path))
        (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")

        def champ(cle: str, valeur: str, sensible: bool) -> Any:
            return (
                SimpleNamespace(group_id=None, resolved_value=valeur),
                SimpleNamespace(
                    page=1,
                    section_id="dep",
                    section_label="Dep",
                    field_key=cle,
                    display_label=cle,
                    value_type="TEXT",
                    polygon=None,
                    sensitive=sensible,
                ),
                True,
            )

        document = (
            SimpleNamespace(id=14, file_name="a.pdf"),
            SimpleNamespace(file_path="a.pdf", page_count=1),
        )

        def archive(requete: str) -> Any:
            db = _db(
                {"DatasetExport": _export()},
                _resultat(all_=[document]),
                _resultat(all_=[champ("dep.nom", "Jean", True), champ("dep.ville", "Lyon", False)]),
            )
            r = _client(SUPERVISEUR, db).get(f"/dataset-exports/8/archive{requete}")
            assert r.status_code == 200
            z = zipfile.ZipFile(io.BytesIO(r.content))
            paires = json.loads(z.read("a.json"))["pages"][0]["sections"][0]["kv_pairs"]
            return json.loads(z.read("manifest.json")), {p["id"]: p.get("value") for p in paires}

        manifest, valeurs = archive("")
        assert valeurs["dep.nom"]["text"] == "Jean" and manifest["sans_sensibles"] is False

        manifest, valeurs = archive("?sans_sensibles=true")
        assert manifest["sans_sensibles"] is True
        assert valeurs["dep.nom"] is None  # le champ reste, sans valeur
        assert valeurs["dep.ville"]["text"] == "Lyon"
