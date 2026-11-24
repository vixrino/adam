"""
Estimation de la taille memoire d'une ligne ORM en octets.

Methode : serialise chaque colonne en sa representation stockee
(string JSON, bytes, int...) et additionne les tailles.

Usage :
    from adam_core.utils.volumetry import estimate_row_size, format_size

    size_bytes = estimate_row_size(dataset)
    print(format_size(size_bytes))  # "1.2 KB"
"""

from datetime import datetime
import json
import sys
from typing import Any, Dict, Sequence

from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase


def estimate_row_size(instance: DeclarativeBase) -> int:
    """
    Estime la taille en octets d'une ligne ORM.

    Ne compte que les colonnes scalaires (pas les relationships).
    Chaque valeur est estimee selon son type de stockage PostgreSQL.

    Returns:
        Taille estimee en octets.
    """
    total = 0
    mapper = inspect(type(instance))

    for column in mapper.columns:
        value = getattr(instance, column.key, None)
        total += _estimate_value(value)

    return total


def estimate_table_size(instances: Sequence[Any]) -> Dict[str, Any]:
    """
    Estime la taille totale d'une liste de lignes ORM.

    Returns:
        Dict avec total_bytes, row_count, avg_bytes_per_row.
    """
    if not instances:
        return {"total_bytes": 0, "row_count": 0, "avg_bytes_per_row": 0}

    sizes = [estimate_row_size(r) for r in instances]
    total = sum(sizes)
    return {
        "total_bytes": total,
        "total_human": format_size(total),
        "row_count": len(instances),
        "avg_bytes_per_row": total // len(instances),
        "avg_human": format_size(total // len(instances)),
        "min_bytes": min(sizes),
        "max_bytes": max(sizes),
    }


def format_size(size_bytes: int) -> str:
    """Convertit des octets en string lisible."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} TB"


def _estimate_value(value: Any) -> int:  # pylint: disable=too-many-return-statements
    """Estime la taille d'une valeur selon son type Python."""

    if value is None:
        return 1  # NULL = 1 octet en PostgreSQL

    if isinstance(value, bool):
        return 1  # BOOLEAN = 1 octet

    if isinstance(value, int):
        return 4  # INTEGER = 4 octets

    if isinstance(value, float):
        return 8  # FLOAT8 = 8 octets

    if isinstance(value, str):
        return len(value.encode("utf-8"))  # VARCHAR = taille reelle UTF-8

    if isinstance(value, datetime):
        return 8  # TIMESTAMPTZ = 8 octets

    if isinstance(value, (dict, list)):
        return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))  # JSONB

    if isinstance(value, bytes):
        return len(value)  # BYTEA

    # Fallback
    return sys.getsizeof(value)
