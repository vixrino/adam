"""Enumerations OCR."""

from enum import Enum


class OcrProvider(str, Enum):
    """Fournisseur OCR."""

    PULSAR = "PULSAR"
    MISTRAL = "MISTRAL"


class StorageMode(str, Enum):
    """Mode de stockage du resultat OCR."""

    JSONB = "JSONB"
    FILE = "FILE"
