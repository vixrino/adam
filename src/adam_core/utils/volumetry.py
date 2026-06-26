"""Estimation de la taille memoire d'une ligne ORM en octets."""

import json
import sys
from datetime import datetime
from typing import Any, Dict, Sequence

from sqlalchemy import inspect
from sqlalchemy.orm import DeclarativeBase


def estimate_row_size(instance: DeclarativeBase) -> int:
    total = 0
    mapper = inspect(type(instance))
    for column in mapper.columns:
        value = getattr(instance, column.key, None)
        total += _estimate_value(value)
    return total


def estimate_table_size(instances: Sequence[Any]) -> Dict[str, Any]:
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
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} TB"


def _estimate_value(value: Any) -> int:  # pylint: disable=too-many-return-statements
    if value is None:
        return 1
    if isinstance(value, bool):
        return 1
    if isinstance(value, int):
        return 4
    if isinstance(value, float):
        return 8
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, datetime):
        return 8
    if isinstance(value, (dict, list)):
        return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    if isinstance(value, bytes):
        return len(value)
    return sys.getsizeof(value)
