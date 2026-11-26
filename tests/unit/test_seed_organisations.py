"""seed_organisations : ne cree que les slugs absents et refuse une liste mal formee."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_organisations.py"


def _script():
    spec = importlib.util.spec_from_file_location("seed_organisations", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_liste_livree_valide_et_contient_dgser():
    script = _script()
    script.verifier(script.ORGANISATIONS)
    assert "dgser" in {slug for slug, _ in script.ORGANISATIONS}


def test_a_creer_ignore_l_existant():
    script = _script()
    orgs = [("dgsi", "DGSI"), ("dgso", "DGSO"), ("dgser", "DGSER")]
    assert script.a_creer(orgs, ["dgso", "bdf"]) == [("dgsi", "DGSI"), ("dgser", "DGSER")]
    assert script.a_creer(orgs, ["dgsi", "dgso", "dgser"]) == []


@pytest.mark.parametrize(
    "orgs",
    [
        [("DGSI", "DGSI")],
        [("dg si", "DGSI")],
        [("dgsi", "DGSI"), ("dgsi", "Autre")],
        [("dgsi", " ")],
    ],
)
def test_verifier_refuse(orgs):
    with pytest.raises(SystemExit):
        _script().verifier(orgs)
