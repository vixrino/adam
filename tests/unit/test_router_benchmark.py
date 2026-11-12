"""Routes du benchmark OCR (recettes, executions, metriques), base simulee."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

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
        assert corps["status"] == "LOCKED" and corps["document_ids"] == [14, 15]
        assert (corps["dataset_export_id"], corps["dataset_id"], corps["version"]) == (8, 4, 1)
        # Le modele d'annotation laisse vide prend celui du .env, fige a la creation.
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
        assert corps["document_ids"] == [14, 15] and corps["status"] == "LOCKED"
        assert corps["config"]["ocr"]["model"] == "mistral-ocr-2"
        assert corps["config"]["ocr"]["provider"] in ("MISTRAL", "MOCK")
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

    def test_recette_brouillon_refusee(self) -> None:
        db = _db({"TestRecipe": _recette("DRAFT")})
        r = _client(SUPERVISEUR, db).post("/test-executions", json={"recipe_id": 3})
        assert r.status_code == 409

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
