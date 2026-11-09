"""PDF du rapport de qualite d'extraction : contenu, filtres, confidentialite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

import pymupdf

from adam_api.services.rapport_metriques_pdf import (
    CHAMPS_AVEC_EXTRAITS,
    extraits_a_montrer,
    rendre_pdf,
)
from adam_core.benchmark.metriques import FiltresChamps, calculer

EXECUTION = {
    "id": 4,
    "recipe_id": 3,
    "status": "COMPLETED",
    "ocr_provider": "mistral",
    "ocr_model_id": "mistral-ocr-latest",
    "comparateur_version": "1",
    "schema_hash": "9e40b5c6aabbcc",
    "finished_at": datetime(2026, 11, 6, 13, 44, tzinfo=timezone.utc),
    "documents_compared": 12,
    "fields_compared": 100,
    "fields_human_verified": 100,
}
EDITE_LE = datetime(2026, 11, 9, tzinfo=timezone.utc)


def _ligne(field_key: str, **comptes: Any) -> Dict[str, Any]:
    return {
        "field_key": field_key,
        "page": 1,
        "section_id": field_key.split(".")[0],
        "value_type": "TEXT",
        "sensitive": False,
        **comptes,
    }


def _lignes() -> List[Dict[str, Any]]:
    return [
        _ligne("deposant.nom", vp=7, fp=2, fn=3, substitutions=2),
        _ligne("gestion_budget.iban", vp=8, fp=1, fn=1, substitutions=1, sensitive=True),
        _ligne("credits.montant", vp=1, fp=3, value_type="NUMBER"),
        _ligne("deposant.ville", vp=12),
    ]


def _texte(pdf: bytes) -> str:
    """Texte du PDF, espaces insecables et ligatures ramenes a la forme simple."""
    document = pymupdf.open("pdf", pdf)
    texte = "\n".join(page.get_text() for page in document)
    return texte.replace("\u00a0", " ").replace("\ufb01", "fi").replace("\ufb02", "fl")


def _rendre(metriques: Dict[str, Any], extraits: Any = None) -> bytes:
    return rendre_pdf(
        metriques,
        recette={"id": 3, "name": "CERFA novembre"},
        dataset="cerfa_13594-02_v2",
        extraits=extraits or {},
        edite_le=EDITE_LE,
    )


def test_entete_taux_et_pied_de_page() -> None:
    pdf = _rendre(calculer(_lignes(), EXECUTION, {"score_minimal": 0.9}))
    assert pdf.startswith(b"%PDF-")
    texte = _texte(pdf)
    assert "Rapport de qualité d'extraction" in texte
    assert "cerfa_13594-02_v2" in texte and "« CERFA novembre »" in texte
    assert "test #4 du 06/11/2026" in texte and "édité le 09/11/2026" in texte
    assert "mistral-ocr-latest" in texte
    # 28 justes sur 28 + 3 fausses + 1 manquee = 32 valeurs remplies
    assert "28 lues correctement sur 32" in texte
    assert "88 %" in texte  # 28 / 32
    assert "Marge d'incertitude" in texte
    assert "échoué" in texte  # score sous 0.9
    assert "schéma 9e40b5c6" in texte and "Page 1 / 1" in texte


def test_filtres_rappeles_et_champs_filtres() -> None:
    filtres = FiltresChamps(reussite_inferieure_a=0.5, types_champ=("NUMBER",))
    texte = _texte(_rendre(calculer(_lignes(), EXECUTION, filtres=filtres)))
    assert "Réussite : < 50 %" in texte and "Type de champ : Nombre" in texte
    assert "1 champ(s)" in texte and "sur 4 vérifiés" in texte
    assert "credits.montant" in texte and "deposant.nom" not in texte
    assert "Lu alors que vide · 3 doc(s) en erreur" in texte


def test_aucun_champ() -> None:
    m = calculer(_lignes(), EXECUTION, filtres=FiltresChamps(recherche="introuvable"))
    assert "Aucun champ ne correspond aux filtres" in _texte(_rendre(m))


def test_extraits_et_champ_sensible_masque() -> None:
    m = calculer(_lignes(), EXECUTION)
    extraits = {
        "deposant.nom": [
            {
                "document_id": 14,
                "page": 1,
                "type_erreur": "fausse",
                "expected_value": "Durand",
                "observed_value": "Dupont",
                "sensitive": False,
            }
        ],
        # Une valeur sensible passee par erreur ne doit jamais s'imprimer.
        "gestion_budget.iban": [
            {
                "document_id": 15,
                "page": 4,
                "type_erreur": "fausse",
                "expected_value": "FR7630006000011234567890189",
                "observed_value": "FR7630006000011234567890180",
                "sensitive": True,
            }
        ],
    }
    texte = _texte(_rendre(m, extraits))
    assert "Document 14 · page 1 · Lu, mais faux" in texte
    assert "Durand" in texte and "Dupont" in texte
    assert "FR76" not in texte and "valeur masquée" in texte
    # 3 documents en erreur sur deposant.nom, 1 montre
    assert "(et 2 autre(s))" in texte


def test_valeurs_echappees() -> None:
    m = calculer(_lignes(), EXECUTION)
    extraits = {
        "deposant.nom": [
            {
                "document_id": 14,
                "page": 1,
                "type_erreur": "fausse",
                "expected_value": "<b>a & b</b>",
                "observed_value": None,
                "sensitive": False,
            }
        ]
    }
    assert "<b>a & b</b>" in _texte(_rendre(m, extraits))


def test_extraits_a_montrer_garde_les_pires_en_erreur() -> None:
    par_champ = [{"champ": f"a.{i}", "documents_en_erreur": i % 2} for i in range(60)]
    choisis = extraits_a_montrer(par_champ)
    assert len(choisis) == CHAMPS_AVEC_EXTRAITS
    assert all(int(c.split(".")[1]) % 2 for c in choisis)


def test_gros_rapport_pagine() -> None:
    """642 champs en erreur : tous listes, sur plusieurs pages numerotees."""
    lignes = [_ligne(f"s{i % 12}.champ_{i}", vp=6, fp=2, fn=2, substitutions=1) for i in range(642)]
    pdf = _rendre(calculer(lignes, EXECUTION))
    total = pymupdf.open("pdf", pdf).page_count
    texte = _texte(pdf)
    assert total > 10 and f"Page {total} / {total}" in texte
    assert all(f"champ_{i}\n" in texte for i in range(642))
