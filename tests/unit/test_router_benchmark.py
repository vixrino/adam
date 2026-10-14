"""Routes du benchmark OCR (recettes, executions, metriques), base simulee."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from adam_api.dependencies.auth import UserCaller, require_user
from adam_api.dependencies.db import get_db
from adam_api.routers.benchmark import router

SUPERVISEUR = UserCaller(matricule="V1", organisation_id=1, platform_role="NOTA_SUPERVISOR")
OPERATEUR = UserCaller(matricule="I1", organisation_id=1)
_NOW = datetime(2026, 10, 13, tzinfo=timezone.utc)


def _resultat(
    *, scalar: Any = None, scalars: Optional[List[Any]] = None, all_: Optional[List[Any]] = None
) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = scalar
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


def _recette(status: str = "LOCKED", config: Optional[Dict[str, Any]] = None) -> Any:
    return SimpleNamespace(
        id=3,
        dataset_id=4,
        name="r",
        description=None,
        document_ids=[14],
        status=status,
        config=config or {},
        locked_at=_NOW,
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


class TestRecettes:
    def test_creation_figee_sur_les_documents_verifies(self) -> None:
        db = _db(
            {"Dataset": SimpleNamespace(id=4)},
            _resultat(scalars=[14, 15]),  # documents avec proposition humaine
            _resultat(scalar=1),  # createur
        )
        r = _client(SUPERVISEUR, db).post(
            "/test-recipes",
            json={"dataset_id": 4, "name": "cerfa", "config": {"score_minimal": 0.9}},
        )
        assert r.status_code == 201, r.text
        corps = r.json()
        assert corps["status"] == "LOCKED" and corps["document_ids"] == [14, 15]
        assert corps["config"]["score_minimal"] == 0.9

    def test_sans_verite_terrain_422(self) -> None:
        db = _db({"Dataset": SimpleNamespace(id=4)}, _resultat(scalars=[]))
        r = _client(SUPERVISEUR, db).post("/test-recipes", json={"dataset_id": 4, "name": "x"})
        assert r.status_code == 422

    def test_recette_figee_non_modifiable(self) -> None:
        db = _db({"TestRecipe": _recette("LOCKED")})
        r = _client(SUPERVISEUR, db).patch("/test-recipes/3", json={"name": "autre"})
        assert r.status_code == 409


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
            _resultat(
                scalars=[
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

    def test_comparaison_n_est_pas_prise_pour_un_id(self) -> None:
        execution = _execution()
        db = _db(
            {"TestExecution": execution, "TestRecipe": _recette()},
            _resultat(scalars=[_rapport("a.b", vp=5)]),
            _resultat(),
            _resultat(scalars=[_rapport("a.b", vp=4, fn=1)]),
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
        db = _db({"TestExecution": _execution()}, _resultat(all_=[(cr, df, fs)]))
        r = _client(SUPERVISEUR, db).get("/test-executions/1/ecarts")
        assert r.status_code == 200, r.text
        ecart = r.json()[0]
        assert ecart["field_key"] == "gestion_budget.iban"
        assert ecart["sensitive"] is True and ecart["expected_value"] is None
