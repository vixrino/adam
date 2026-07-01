"""Utilitaire de parsing de valeur de champ selon son FieldValueType.

Tolérant par design : aucun cas ne lève d'exception vers l'appelant.
Réutilisable par la sérialisation API, les workers, et toute logique
ayant besoin d'interpréter une valeur brute stockée en base.

Les documents traités étant en français, DATE/DATETIME/NUMBER acceptent
en plus les formats FR usuels (JJ/MM/AAAA, "1 234,56") en repli lorsque
le format ISO 8601 / anglo-saxon ne correspond pas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from adam_core.enums.status import FieldValueType

_FRENCH_DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y")
_FRENCH_DATETIME_FORMATS = (
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
)
_THOUSAND_SEPARATORS = (" ", " ", " ")


def _normalize_french_number(raw: str) -> str:
    """Retire les séparateurs de milliers FR et convertit la virgule décimale en point."""
    s = raw.strip()
    for sep in _THOUSAND_SEPARATORS:
        s = s.replace(sep, "")
    if "," in s:
        s = s.replace(".", "")  # points restants = separateurs de milliers ("1.234,56")
        s = s.replace(",", ".")
    return s


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
        normalized = _normalize_french_number(raw)
        try:
            return int(normalized)
        except (ValueError, TypeError):
            pass
        try:
            return float(normalized)
        except (ValueError, TypeError):
            pass
        return raw
    if value_type == FieldValueType.DATE.value:
        try:
            return datetime.fromisoformat(raw).date().isoformat()
        except (ValueError, TypeError):
            pass
        for fmt in _FRENCH_DATE_FORMATS:
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except (ValueError, TypeError):
                continue
        return raw
    if value_type == FieldValueType.DATETIME.value:
        try:
            return datetime.fromisoformat(raw).isoformat()
        except (ValueError, TypeError):
            pass
        for fmt in _FRENCH_DATETIME_FORMATS:
            try:
                return datetime.strptime(raw, fmt).isoformat()
            except (ValueError, TypeError):
                continue
        return raw
    return raw
