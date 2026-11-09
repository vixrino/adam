"""Scripts du benchmark : repartition des cas de la demo et lecture du .env.

La demo doit produire un score ni nul ni parfait : chaque sorte de cas
(juste, fausse, manquee, inventee, vide) y figure, sinon le JSON ne montre
pas a quoi ressemblent des metriques reelles.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _charger(nom: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(nom, SCRIPTS / f"{nom}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


def test_la_repartition_couvre_chaque_sorte_de_cas() -> None:
    demo = _charger("demo_metriques")
    champs = [(i, f"section.champ_{i}") for i in range(40)]
    detectees, verite = demo.repartir(champs)

    lues = set(detectees)
    justes = sum(1 for i, c in champs if c in lues and verite[i] == demo.VALEUR_LUE)
    fausses = sum(1 for i, c in champs if c in lues and verite[i] not in (None, demo.VALEUR_LUE))
    inventees = sum(1 for i, c in champs if c in lues and verite[i] is None)
    manquees = sum(1 for i, c in champs if c not in lues and verite[i] is not None)
    vides = sum(1 for i, c in champs if c not in lues and verite[i] is None)
    assert (justes, fausses, manquees, inventees, vides) == (24, 4, 4, 4, 4)


def test_la_base_de_demo_n_est_jamais_la_base_de_travail() -> None:
    demo = _charger("demo_metriques")
    for base in ("nota_db", "nota_db" + demo.SUFFIXE_BASE):
        cible = base.removesuffix(demo.SUFFIXE_BASE) + demo.SUFFIXE_BASE
        assert cible == "nota_db_demo_metriques"


def test_lire_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    demo = _charger("demo_metriques")
    (tmp_path / ".env").write_text('APP_ENV=dev\nPOSTGRES_DB="nota_db"\n', encoding="utf-8")
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    assert demo._lire_env("POSTGRES_DB") == "nota_db"
    assert demo._lire_env("ABSENTE") == ""


def test_lister_ids_trouve_le_paquet_core() -> None:
    assert _charger("lister_ids_benchmark")._paquet_core() == "adam_core"
