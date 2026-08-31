"""Interface commune aux connecteurs OCR.

Un connecteur recoit les images d'un document et rend un SmartdocDocument, le
contrat d'interface v0.3 deja utilise par l'ingestion et le seed. Retourner ce
type plutot qu'un dictionnaire brut fait porter la validation au connecteur :
en aval, le merger travaille sur des KVPair valides et n'a pas a se defendre
contre une reponse malformee.

`extract` peut rendre None. C'est un cas nominal, pas une erreur : un moteur OCR
indisponible ou incapable de traiter un document doit laisser la chaine
continuer, le document etant alors pre-alimente avec des champs vides plutot que
mis en echec. Les vraies erreurs, elles, levent OcrConnectorError.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Sequence

from adam_core.schemas.interface_contract import SmartdocDocument


class OcrConnectorError(Exception):
    """Echec technique du connecteur : moteur injoignable, reponse illisible.

    A distinguer d'un `extract` rendant None, qui signale une absence de
    resultat sans incident.
    """


class BaseOcrConnector(ABC):
    """Sous-classer et implementer `extract`."""

    #: Nom court, pour les logs et la tracabilite.
    name: str = "base"

    @abstractmethod
    async def extract(self, images: Sequence[Path]) -> Optional[SmartdocDocument]:
        """Soumet les images au moteur et rend le document structure.

        Args:
            images: chemins des images de page, dans l'ordre des pages.

        Returns:
            Le document OCR, ou None si le moteur n'a rien produit.

        Raises:
            OcrConnectorError: echec technique.
        """
