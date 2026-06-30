"""Utilitaire de parsing de valeur de champ selon son FieldValueType.

Tolérant par design : aucun cas ne lève d'exception vers l'appelant.
Réutilisable par la sérialisation API, les workers, et toute logique
ayant besoin d'interpréter une valeur brute stockée en base.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from adam_core.enums.status import FieldValueType


def parse_field_value(raw: Optional[str], value_type: Optional[str]) -> Any:
    """Convertit une valeur brute string selon son FieldValueType.

    Retourne la valeur convertie dans son type natif Python/JSON quand
    la conversion est possible, sinon retourne raw tel quel sans erreur.
    """
    if raw is None or value_type is None:
        return raw
    if not isinstance(raw, str):
        return raw
    if value_type == FieldValueType.TEXT.value:
        return raw
    if value_type == FieldValueType.BOOLEAN.value:
        return raw.strip().lower() in {"true", "1", "yes", "oui"}
    if value_type == FieldValueType.NUMBER.value:
        try:
            return int(raw)
        except (ValueError, TypeError):
            pass
        try:
            return float(raw)
        except (ValueError, TypeError):
            pass
        return raw
    if value_type == FieldValueType.DATE.value:
        try:
            return datetime.fromisoformat(raw).date().isoformat()
        except (ValueError, TypeError):
            return raw
    if value_type == FieldValueType.DATETIME.value:
        try:
            return datetime.fromisoformat(raw).isoformat()
        except (ValueError, TypeError):
            return raw
    return raw
