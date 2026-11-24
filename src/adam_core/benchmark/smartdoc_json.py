"""Passage de benchmark a partir de JSON deja produits par un moteur externe (SMARTDOC).

Au lieu de lire les images avec Mistral, le passage compare la verite humaine a
des JSON au contrat Smartdoc v0.3, deposes au lancement. Chaque JSON est relie
a un document de la recette par son nom : ``dossier.json`` <-> ``dossier.pdf``
(la casse et l'extension ne comptent pas, ``dossier.pdf.json`` est accepte).

Les JSON sont gardes avec le passage, sous le PVC : le rapport reste
auditable (quel fichier a donne ce score).
"""

from __future__ import annotations

from pathlib import Path

from adam_core.enums.ocr import OcrProvider

FOURNISSEUR = OcrProvider.SMARTDOC_JSON.value
META = "_meta.json"


def dossier(execution_id: int) -> Path:
    """Ou sont gardes les JSON d'un passage, relativement a la racine du PVC."""
    return Path("benchmark") / "smartdoc_json" / str(execution_id)


def cle(nom: str) -> str:
    """Ce qui relie un JSON a son document : le nom sans extensions, en minuscules."""
    base = Path(nom).name.casefold()
    for extension in (".json", ".pdf"):
        if base.endswith(extension):
            base = base[: -len(extension)]
    return base
