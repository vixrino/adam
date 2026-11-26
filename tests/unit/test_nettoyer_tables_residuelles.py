"""scripts/nettoyer_tables_residuelles.py, contre une base SQLite a deux schemas.

Deux bases en memoire, attachees sous les noms « public » et « nota », jouent
les deux schemas PostgreSQL de nota. La protection propre a PostgreSQL (DROP
refuse sans CASCADE quand une autre table depend de la table visee) n'est pas
rejouable ici : ce test couvre le choix des tables, le comptage et la
suppression.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Iterator

import pytest
from sqlalchemy import create_engine, event, inspect, text

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "nettoyer_tables_residuelles.py"


def _script() -> Any:
    spec = importlib.util.spec_from_file_location("nettoyer_tables_residuelles", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["nettoyer_tables_residuelles"] = module
    spec.loader.exec_module(module)
    return module


script = _script()

TABLES_APPLICATION = ["doc_schema", "field_spec", "schema_page", "dataset"]


@pytest.fixture(name="connexion")
def _connexion_fixture() -> Iterator[Any]:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _attacher(dbapi_connexion: Any, _: Any) -> None:
        dbapi_connexion.execute("ATTACH DATABASE ':memory:' AS public")
        dbapi_connexion.execute("ATTACH DATABASE ':memory:' AS nota")

    with engine.begin() as conn:
        for schema in ("public", "nota"):
            conn.execute(text(f"CREATE TABLE {schema}.doc_schema (id INTEGER PRIMARY KEY)"))
            conn.execute(
                text(
                    f"CREATE TABLE {schema}.field_spec (id INTEGER PRIMARY KEY, "
                    f"schema_id INTEGER REFERENCES doc_schema(id))"
                )
            )
        conn.execute(text("CREATE TABLE nota.dataset (id INTEGER PRIMARY KEY)"))
        # Ce que public porte d'autre : a ne jamais toucher.
        conn.execute(text("CREATE TABLE public.alembic_version (version_num TEXT)"))
        conn.execute(text("CREATE TABLE public.autre_application (id INTEGER)"))
        conn.execute(text("INSERT INTO public.doc_schema (id) VALUES (11)"))
        conn.execute(text("INSERT INTO public.field_spec (id, schema_id) VALUES (1, 11)"))
        conn.execute(text("INSERT INTO nota.doc_schema (id) VALUES (1), (2), (3)"))
        yield conn


def test_ne_vise_que_les_noms_de_l_application() -> None:
    assert script.noms_residuels(
        ["doc_schema", "alembic_version", "autre_application", "field_spec"],
        TABLES_APPLICATION,
    ) == ["doc_schema", "field_spec"]


def test_recense_les_lignes_de_part_et_d_autre(connexion: Any) -> None:
    tables = script.recenser(connexion, "nota", TABLES_APPLICATION)

    assert tables == [
        script.TableResiduelle("doc_schema", lignes_residuelles=1, lignes_application=3),
        script.TableResiduelle("field_spec", lignes_residuelles=1, lignes_application=0),
    ]


def test_table_absente_du_schema_de_l_application(connexion: Any) -> None:
    connexion.execute(text("CREATE TABLE public.dataset (id INTEGER)"))
    connexion.execute(text("DROP TABLE nota.dataset"))

    tables = {t.nom: t for t in script.recenser(connexion, "nota", TABLES_APPLICATION)}

    assert tables["dataset"].lignes_application is None


def test_supprime_les_residuelles_et_rien_d_autre(connexion: Any) -> None:
    script.supprimer(connexion, ["doc_schema", "field_spec"])

    inspecteur = inspect(connexion)
    assert sorted(inspecteur.get_table_names(schema="public")) == [
        "alembic_version",
        "autre_application",
    ]
    assert sorted(inspecteur.get_table_names(schema="nota")) == [
        "dataset",
        "doc_schema",
        "field_spec",
    ]
    assert connexion.execute(text("SELECT count(*) FROM nota.doc_schema")).scalar_one() == 3


def test_affichage(capsys: pytest.CaptureFixture[str]) -> None:
    script.afficher(
        [
            script.TableResiduelle("doc_schema", 1, 3),
            script.TableResiduelle("dataset", 4, None),
        ],
        "nota",
    )

    sortie = capsys.readouterr().out
    assert "lignes public" in sortie and "lignes nota" in sortie
    assert "absente" in sortie
