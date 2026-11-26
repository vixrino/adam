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
    def __init__(self, valeur: bool, schemas: list[str]) -> None:
        self.valeur = valeur
        self.schemas = schemas

    def scalar_one(self) -> bool:
        return self.valeur

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter([(s,) for s in self.schemas])


class _Connexion:
    """Base ou tout existe dans chaque schema, sauf les (schema, table, colonne) absents."""

    def __init__(self, schemas: list[str], absentes: set[tuple[str, str, str]]) -> None:
        self.schemas = schemas
        self.absentes = absentes

    async def __aenter__(self) -> "_Connexion":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, _requete: object, params: dict | None = None) -> _Resultat:
        if params is None:
            return _Resultat(True, self.schemas)
        cle = (params["s"], params["t"], params.get("c", ""))
        return _Resultat(cle not in self.absentes, self.schemas)


class _Moteur:
    def __init__(self, schemas: list[str], absentes: set[tuple[str, str, str]]) -> None:
        self.schemas = schemas
        self.absentes = absentes

    def connect(self) -> _Connexion:
        return _Connexion(self.schemas, self.absentes)

    async def dispose(self) -> None:
        return None


async def test_une_colonne_metrique_absente_rend_la_base_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # test_recipe.config present, test_execution.comparateur_version absent.
    script = _script()
    absentes = {("public", "test_execution", "comparateur_version")}
    monkeypatch.setattr(script, "_engine", lambda _core: _Moteur(["public"], absentes))
    etat = await script._etat("adam_core")
    assert etat["metriques"] is False
    assert etat["schema_page"] is True


async def test_un_schema_en_retard_suffit_a_rendre_la_base_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Cas reel nota : public a jour, nota (lu par le worker) sans la colonne.
    script = _script()
    absentes = {("nota", "test_execution", "comparateur_version")}
    moteur = _Moteur(["nota", "public"], absentes)
    monkeypatch.setattr(script, "_engine", lambda _core: moteur)
    assert (await script._etat("nota_core"))["metriques"] is False


async def test_toutes_les_colonnes_metriques_presentes(monkeypatch: pytest.MonkeyPatch) -> None:
    script = _script()
    monkeypatch.setattr(script, "_engine", lambda _core: _Moteur(["nota", "public"], set()))
    assert (await script._etat("adam_core"))["metriques"] is True


def test_ddl_metriques_joue_le_ddl_direct_du_paquet_trouve(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = importlib.util.spec_from_file_location(
        "ddl_metriques", SCRIPT.parent / "ddl_metriques.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    appels: list[str] = []

    async def _ddl(core: str) -> list[str]:
        appels.append(core)
        return ["public", "nota"]

    monkeypatch.setattr(module.migrer, "_paquet_core", lambda: ("nota_core", Path("x")))
    monkeypatch.setattr(module.migrer, "_ddl_direct", _ddl)
    module.main()
    assert appels == ["nota_core"]
    assert (
        "nota_core : colonnes des metriques en place dans public, nota" in capsys.readouterr().out
    )
