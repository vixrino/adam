"""
Énumérations liées aux moteurs OCR et au mode de stockage
des résultats OCR.
"""

from enum import Enum


class OcrProvider(str, Enum):  # pylint: disable=invalid-name
    """Fournisseurs OCR supportés pour la pré-alimentation des datasets."""

    PULSAR = "PULSAR"  # pylint: disable=invalid-name
    MISTRAL = "MISTRAL"  # pylint: disable=invalid-name


class StorageMode(str, Enum):  # pylint: disable=invalid-name
    """
    Mode de stockage du résultat JSON brut OCR dans OCR_RESULT.

    - JSONB : le JSON est stocké directement en base
    - FILE  : le JSON est stocké sur PVC
    """

    JSONB = "JSONB"  # pylint: disable=invalid-name
    FILE = "FILE"  # pylint: disable=invalid-name
