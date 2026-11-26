"""Contrat de sortie du benchmark : les modeles Pydantic couvrent exactement
ce que calculer() et comparer() rendent.

extra="forbid" : une cle ajoutee au calcul sans etre declaree dans
adam_api/schemas/benchmark.py fait echouer ces tests, comme une cle declaree
qui n'est plus rendue.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import pytest
from pydantic import ValidationError

from adam_api.schemas.benchmark import ComparaisonOut, MetriquesOut
from adam_core.benchmark.metriques import FiltresChamps, calculer, comparer

EXECUTION = {
    "id": 1,
    "recipe_id": 3,
    "status": "COMPLETED",
    "ocr_provider": "MISTRAL",
    "ocr_model_id": "ocr-1 + annot-1",
    "comparateur_version": "1",
    "schema_hash": "abc",
    "verite_hash": "v1",
    "started_at": datetime(2026, 11, 12, tzinfo=timezone.utc),
    "finished_at": datetime(2026, 11, 12, tzinfo=timezone.utc),
    "documents_compared": 12,
    "fields_compared": 100,
    "fields_human_verified": 90,
    "ocr_calls_made": 360,
    "pages_processed": 144,
    "error_message": "documents ecartes, images de page absentes : [3]",
}
# Toutes les branches remplies : seuils franchis, filtres actifs, champ
# sensible, montant, libelle de section.
CONFIG = {
    "score_minimal": 0.99,
    "seuils_par_champ": {"deposant.nom": 0.01},
    "seuils_par_categorie": {"sensible": 0.0},
    "champs_exclus": ["interne."],
}
RECETTE = {
    "id": 3,
    "name": "cerfa",
    "version": 2,
    "dataset_export_id": 8,
    "document_ids": [14, 15],
}


def _ligne(field_key: str, **autres: Any) -> Dict[str, Any]:
    base = {
        "field_key": field_key,
        "page": 1,
        "section_id": field_key.split(".")[0],
        "section_label": "Deposant",
        "value_type": "TEXT",
        "sensitive": False,
    }
    return {**base, **autres}


def _metriques(**execution: Any) -> Dict[str, Any]:
    m = calculer(
        [
            _ligne("deposant.nom", vp=8, fn=2, somme_distance=3, somme_longueur_attendue=40),
            _ligne("deposant.iban", vp=1, fp=1, fn=1, substitutions=1, sensitive=True),
            _ligne("budget.montant", page=4, value_type="NUMBER", vp=3, vn=1),
            _ligne("interne.code", vp=1),
        ],
        dict(EXECUTION, **execution),
        CONFIG,
        {"DIGIT": 1, "MISSING": 2},
        tous_les_champs=True,
        filtres=FiltresChamps(recherche="deposant", types_erreur=("manquee",)),
    )
    m["recette"] = RECETTE
    m["dataset"] = {"id": 4, "name": "CERFA novembre"}
    return m


def test_metriques_conformes_au_contrat() -> None:
    m = _metriques()
    sortie = MetriquesOut.model_validate(m).model_dump(by_alias=True)
    # Rien de perdu au passage : memes cles a la racine, et dans chaque champ.
    assert set(sortie) == set(m)
    assert set(sortie["par_champ"][0]) >= set(m["par_champ"][0])
    assert sortie["verdict"]["categories_en_echec"] and sortie["verdict"]["champs_en_echec"]


def test_cle_non_declaree_refusee() -> None:
    m = _metriques()
    m["global"]["nouvel_indicateur"] = 1
    with pytest.raises(ValidationError):
        MetriquesOut.model_validate(m)


def test_comparaison_conforme_au_contrat() -> None:
    a = _metriques()
    b = _metriques(id=2, ocr_model_id="ocr-2 + annot-1", verite_hash="v2")
    c = comparer(a, b)
    sortie = ComparaisonOut.model_validate(c).model_dump(by_alias=True)
    assert set(sortie) == set(c)
    assert sortie["moteur"]["changements"] == ["modele"]
    assert sortie["b"]["recette"]["version"] == 2
