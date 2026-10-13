"""Le script de migration genere des migrations valides, pour chaque changement.

Un gabarit contenant des accolades ('{}'::jsonb) faisait echouer .format() au
moment d'ecrire la migration, sur le poste de l'utilisateur et non ici : chaque
gabarit est donc rendu et compile par ce test.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrer_expected_page_count.py"


def _script():
    spec = importlib.util.spec_from_file_location("migrer_script", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Une @dataclass cherche son module dans sys.modules.
    sys.modules["migrer_script"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("index", range(3))
def test_chaque_gabarit_donne_une_migration_valide(index: int) -> None:
    script = _script()
    changement = script.CHANGEMENTS[index]
    texte = changement.contenu.format(revision="abc123", down_revision="def456")
    arbre = ast.parse(texte)
    noms = {n.name for n in arbre.body if isinstance(n, ast.FunctionDef)}
    assert noms == {"upgrade", "downgrade"}
    assert 'revision: str = "abc123"' in texte
    assert 'down_revision: Union[str, None] = "def456"' in texte
    # La migration ecrite est reconnue comme couvrant son changement.
    assert changement.deja_couvert(texte)


def test_le_defaut_jsonb_survit_au_rendu() -> None:
    texte = _script().MIGRATION_METRIQUES.format(revision="a", down_revision="b")
    assert "'{}'::jsonb" in texte
