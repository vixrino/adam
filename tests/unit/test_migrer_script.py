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


def test_chaque_colonne_metrique_est_creee_par_le_ddl_direct() -> None:
    script = _script()
    ddl = " ".join(script.DDL_DIRECT)
    for table, colonne in script.COLONNES_METRIQUES:
        assert f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {colonne} " in ddl


class _Resultat:
    def __init__(self, valeur: bool) -> None:
        self.valeur = valeur

    def scalar_one(self) -> bool:
        return self.valeur


class _Connexion:
    """Base ou toutes les colonnes existent, sauf celles de `absentes`."""

    def __init__(self, absentes: set[tuple[str, str]]) -> None:
        self.absentes = absentes

    async def __aenter__(self) -> "_Connexion":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, _requete: object, params: dict | None = None) -> _Resultat:
        if params is None:
            return _Resultat(True)
        return _Resultat((params["t"], params["c"]) not in self.absentes)


class _Moteur:
    def __init__(self, absentes: set[tuple[str, str]]) -> None:
        self.absentes = absentes

    def connect(self) -> _Connexion:
        return _Connexion(self.absentes)

    async def dispose(self) -> None:
        return None


async def test_une_colonne_metrique_absente_rend_la_base_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Cas reel : test_recipe.config present, test_execution.comparateur_version absent.
    script = _script()
    absentes = {("test_execution", "comparateur_version")}
    monkeypatch.setattr(script, "_engine", lambda _core: _Moteur(absentes))
    etat = await script._etat("adam_core")
    assert etat["metriques"] is False
    assert etat["schema_page"] is True


async def test_toutes_les_colonnes_metriques_presentes(monkeypatch: pytest.MonkeyPatch) -> None:
    script = _script()
    monkeypatch.setattr(script, "_engine", lambda _core: _Moteur(set()))
    assert (await script._etat("adam_core"))["metriques"] is True
