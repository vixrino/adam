"""PDF du rapport de qualite d'extraction : contenu, filtres, pages, confidentialite.

Le rendu visuel (cotes, couleurs, polices) est compare a la maquette hors des
tests ; ici, ce que le PDF dit.
"""

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
        "section_label": field_key.split(".")[0].capitalize(),
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
    """Texte du PDF, ligatures ramenees a la forme simple."""
    document = pymupdf.open("pdf", pdf)
    texte = "\n".join(page.get_text() for page in document)
    return texte.replace("ﬁ", "fi").replace("ﬂ", "fl")


def _rendre(metriques: Dict[str, Any], extraits: Any = None) -> bytes:
    return rendre_pdf(
        metriques,
        recette={"id": 3},
        dataset="cerfa_13594-02_v2",
        extraits=extraits or {},
        edite_le=EDITE_LE,
    )


def _ecart(document_id: int, attendu: Any, lu: Any, sensible: bool = False) -> Dict[str, Any]:
    return {
        "document_id": document_id,
        "page": 1,
        "type_erreur": "fausse",
        "expected_value": attendu,
        "observed_value": lu,
        "sensitive": sensible,
    }


def test_entete_taux_et_pied_de_page() -> None:
    pdf = _rendre(calculer(_lignes(), EXECUTION))
    assert pdf.startswith(b"%PDF-")
    texte = _texte(pdf)
    assert "NOTA · Rapport de qualité d'extraction" in texte
    assert "Dataset cerfa_13594-02_v2 · recette #3" in texte
    assert "Moteur : mistral · 12 documents" in texte and "Édité le 09/11/2026" in texte
    # Taux de lectures justes = global.taux_lectures_justes, le champ que lit la
    # page : 28 justes sur 34 ecrites (28 + 3 fausses + 3 inventees). Donnees
    # asymetriques (1 manquee, 3 inventees) : le rappel, 28/32, donnerait 88 %.
    assert "Taux de lectures justes" in texte
    assert "· 28 lus correctement sur 34" in texte
    assert "82 %" in texte and "88 %" not in texte
    assert "Marge d'incertitude : " in texte
    assert "Généré par NOTA · comparateur v1 · schéma 9e40b5c6" in texte
    assert "Page 1 / 1" in texte


def test_tableau_libelles_de_la_maquette() -> None:
    texte = _texte(_rendre(calculer(_lignes(), EXECUTION)))
    for titre in ("Champ", "Type", "Réussite", "Échec principal"):
        assert titre in texte
    assert "Deposant" in texte  # libelle de section du schema
    assert "NOMBRE" in texte and "TEXTE" in texte
    assert "Inventé" in texte and "Lu mais faux" in texte


def test_filtres_rappeles_et_champs_filtres() -> None:
    filtres = FiltresChamps(reussite_inferieure_a=0.5, types_champ=("NUMBER",))
    texte = _texte(_rendre(calculer(_lignes(), EXECUTION, filtres=filtres)))
    assert "Filtres appliqués à ce rapport" in texte
    assert "Réussite : < 50 % · Type de champ : NOMBRE · Type d'erreur : tous ·" in texte
    assert "1 champ" in texte and "sur 4 vérifiés" in texte
    assert "credits.montant" in texte and "deposant.nom" not in texte


def test_aucun_champ() -> None:
    m = calculer(_lignes(), EXECUTION, filtres=FiltresChamps(recherche="introuvable"))
    assert "Aucun champ ne correspond aux filtres" in _texte(_rendre(m))


def test_extraits_et_champ_sensible_masque() -> None:
    m = calculer(_lignes(), EXECUTION)
    extraits = {
        "deposant.nom": [_ecart(14, "Durand", "Dupont")],
        # Une valeur sensible passee par erreur ne doit jamais s'imprimer.
        "gestion_budget.iban": [
            _ecart(15, "FR7630006000011234567890189", "FR7630006000011234567890180", True)
        ],
        "credits.montant": [_ecart(16, None, "1200")],
    }
    texte = _texte(_rendre(m, extraits))
    assert "Extraits de documents en erreur" in texte
    assert "Doc #14 · page 1" in texte
    assert "Durand" in texte and "Dupont" in texte
    assert "FR76" not in texte and "(masquée)" in texte
    assert "(vide)" in texte


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
    assert "Champs en erreur (suite)" in texte
    assert all(f"champ_{i}\n" in texte for i in range(642))


def test_cle_trop_longue_coupee_dans_sa_colonne() -> None:
    cle = "prestations_familiales.co_deposant_msa_numero_allocataire[ligne_12]"
    pdf = _rendre(calculer([_ligne(cle, vp=1, fn=1)], EXECUTION))
    page = pymupdf.open("pdf", pdf)[0]
    # La colonne Champ s'arrete a 392,3 px de maquette.
    limite = 392.3 * page.rect.width / 794
    spans = [
        s
        for b in page.get_text("dict")["blocks"]
        for l in b.get("lines", [])
        for s in l["spans"]
        if s["text"] and s["text"] in cle
    ]
    assert len(spans) >= 2 and all(s["bbox"][2] <= limite for s in spans)


def test_sans_fichier_de_police_les_polices_integrees(monkeypatch: Any) -> None:
    """Un depot sans le dossier polices/ rend quand meme le PDF, en Helvetica."""
    from adam_api.services import rapport_metriques_pdf as module

    for nom in ("_REGULIER", "_MOYEN", "_DEMI_GRAS", "_GRAS", "_FIXE"):
        police = getattr(module, nom)
        sans = module._Police(  # pylint: disable=protected-access
            police.nom, "absente.ttf", police.interne, crenage=police.crenage
        )
        monkeypatch.setattr(module, nom, sans)
    m = calculer(_lignes(), EXECUTION)
    pdf = _rendre(m, {"deposant.nom": [_ecart(14, "Durand", "Dupont")]})
    texte = _texte(pdf)
    assert "Rapport de qualité d'extraction" in texte and "Doc #14 · page 1" in texte
    polices = {f[3] for f in pymupdf.open("pdf", pdf)[0].get_fonts()}
    # Les polices integrees de MuPDF : Nimbus Sans (Helvetica) et Nimbus Mono.
    assert any("Nimbus Sans" in p for p in polices) and not any("Inter" in p for p in polices)


def test_filtre_section_par_son_libelle() -> None:
    m = calculer(_lignes(), EXECUTION, filtres=FiltresChamps(sections=("gestion_budget",)))
    texte = _texte(_rendre(m))
    assert "Section : Gestion_budget" in texte  # libelle du schema, pas l'id


def test_ligne_des_filtres_longue_passe_a_la_ligne() -> None:
    lignes = [_ligne(f"section_au_libelle_tres_long_{i}.champ", vp=1, fn=1) for i in range(6)]
    sections = tuple(f"section_au_libelle_tres_long_{i}" for i in range(6))
    pdf = _rendre(calculer(lignes, EXECUTION, filtres=FiltresChamps(sections=sections)))
    page = pymupdf.open("pdf", pdf)[0]
    droite = 738 * page.rect.width / 794
    spans = [
        s for b in page.get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]
    ]
    assert "6 champs" in _texte(pdf)
    # Un demi-point de tolerance : un texte aligne a droite finit pile sur la
    # marge, et le contour d'un glyphe Helvetica (polices integrees, sans les
    # fichiers de polices/) la depasse d'une fraction invisible.
    assert all(s["bbox"][2] <= droite + 0.5 for s in spans if s["text"].strip())
