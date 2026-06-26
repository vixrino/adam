"""Utilitaires de hachage SHA-256 partages (ingestion JSON et PDF)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Union

_CHUNK_SIZE = 1024 * 1024  # 1 MiB


def sha256_bytes(data: bytes) -> str:
    """Retourne le SHA-256 hexadecimal (64 caracteres) d'un contenu en memoire."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Union[str, Path]) -> str:
    """Retourne le SHA-256 hexadecimal d'un fichier lu par blocs."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
