"""Connecteur « SMARTDOC_JSON » : relit des JSON deja produits, sans toucher aux images.

Il ne passe pas par ``extract`` : le worker de benchmark lui demande le JSON d'un
document par son nom (``read``). Un document sans JSON rend None.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Sequence

from adam_core.benchmark.smartdoc_json import META, cle
from adam_core.schemas.interface_contract import SmartdocDocument
from adam_worker.connectors.base import BaseOcrConnector, DocumentNonConforme
from adam_worker.connectors.modele import ModeleDocument


class SmartdocJsonConnector(BaseOcrConnector):
    name = "smartdoc_json"
    #: Lu par le worker comme les autres connecteurs : va sur l'execution.
    model: Optional[str] = None

    def __init__(self, racine: Path) -> None:
        self.racine = racine
        self.fichiers: Dict[str, Path] = {
            cle(p.name): p for p in sorted(racine.glob("*.json")) if p.name != META
        }
        meta = racine / META
        libelle = None
        if meta.is_file():
            libelle = json.loads(meta.read_text(encoding="utf-8")).get("libelle")
        self.model = libelle or f"{len(self.fichiers)} json"

    def read(self, nom_fichier: str) -> Optional[SmartdocDocument]:
        """Le JSON du document, ou None s'il n'en a pas. Illisible : DocumentNonConforme."""
        chemin = self.fichiers.get(cle(nom_fichier))
        if chemin is None:
            return None
        try:
            return SmartdocDocument.model_validate_json(chemin.read_bytes())
        except ValueError as exc:
            raise DocumentNonConforme(f"{chemin.name} : {exc}", []) from exc

    async def extract(
        self, images: Sequence[Path], modele: Optional[ModeleDocument] = None
    ) -> Optional[SmartdocDocument]:
        raise NotImplementedError("SMARTDOC_JSON se lit par nom de fichier : voir read()")
