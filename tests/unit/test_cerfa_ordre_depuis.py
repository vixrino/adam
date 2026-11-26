"""Schema CERFA : ordre du formulaire, une date par statut, conversion d'une base."""

import importlib.util
from pathlib import Path

from adam_core.schemas.cerfa_v2 import CERFA_V2_PAGE_FIELDS

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "migrer_schema_ordre_depuis.py"
_spec = importlib.util.spec_from_file_location("migrer_ordre", _SCRIPT)
migrer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migrer)  # type: ignore[union-attr]


def _sections(page: int) -> list:
    vues: list = []
    for cle in CERFA_V2_PAGE_FIELDS[page]:
        section = cle.split(".", 1)[0]
        if section not in vues:
            vues.append(section)
    return vues


def test_page_4_gestion_du_budget_avant_les_vehicules() -> None:
    sections = _sections(4)
    assert sections.index("gestion_budget") < sections.index("vehicules")


def test_page_11_cause_en_fin_de_page() -> None:
    assert _sections(11)[-1] == "cause_surendettement"


def test_page_3_chaque_statut_suivi_de_sa_date() -> None:
    cles = [c.split(".", 1)[1] for c in CERFA_V2_PAGE_FIELDS[3] if "statut_" in c]
    for i, cle in enumerate(cles):
        if not cle.endswith(("_depuis", "_precision")):
            assert cles[i + 1] == f"{cle}_depuis"
    assert not any(c.endswith(".deposant_depuis") for c in CERFA_V2_PAGE_FIELDS[3])


def test_date_a_la_premiere_case_cochee() -> None:
    ordre = ["s_cdi", "s_cdd", "s_etudiant"]
    assert migrer.cible_date(ordre, {"s_cdd": "true", "s_etudiant": "true"}) == ("s_cdd", 2)
    assert migrer.cible_date(ordre, {"s_cdi": "false", "s_etudiant": "true"}) == ("s_etudiant", 1)
    assert migrer.cible_date(ordre, {"s_cdi": None}) == (None, 0)
