"""Utilitaire de parsing de valeur de champ selon son FieldValueType.

Tolérant par design : aucun cas ne lève d'exception vers l'appelant.
Réutilisable par la sérialisation API, les workers, et toute logique
ayant besoin d'interpréter une valeur brute stockée en base.

Les documents traités étant en français, DATE/DATETIME/NUMBER acceptent
en plus les formats FR usuels (JJ/MM/AAAA, "1 234,56") en repli lorsque
le format ISO 8601 / anglo-saxon ne correspond pas.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Optional

from adam_core.enums.status import FieldValueType

_DATE_SEPARATORS = ("/", "-", ".", " ")
_TIME_FORMATS = ("%H:%M:%S", "%H:%M")


def _date_formats(year_directive: str) -> tuple[str, ...]:
    return tuple(f"%d{sep}%m{sep}{year_directive}" for sep in _DATE_SEPARATORS)


def _datetime_formats(year_directive: str) -> tuple[str, ...]:
    return tuple(
        f"%d{sep}%m{sep}{year_directive} {time_fmt}"
        for sep in _DATE_SEPARATORS
        for time_fmt in _TIME_FORMATS
    )


_FRENCH_DATE_FORMATS = _date_formats("%Y")
_FRENCH_DATETIME_FORMATS = _datetime_formats("%Y")
_THOUSAND_SEPARATORS = (" ", "\xa0", " ")  # espace, espace insecable, espace fine insecable


def _normalize_french_number(raw: str) -> str:
    """Retire les séparateurs de milliers FR et convertit la virgule décimale en point."""
    s = raw.strip()
    for sep in _THOUSAND_SEPARATORS:
        s = s.replace(sep, "")
    if "," in s:
        s = s.replace(".", "")  # points restants = separateurs de milliers ("1.234,56")
        s = s.replace(",", ".")
    return s


def _try_number(s: str) -> Optional[Any]:
    """Tente int puis float ; rejette nan/inf, non representables en JSON strict."""
    try:
        return int(s)
    except (ValueError, TypeError):
        pass
    try:
        value = float(s)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(value):
        return None
    return value


_TRUTHY = frozenset({"true", "1", "yes", "oui"})


def _parse_boolean(raw: str) -> Any:
    return raw.strip().lower() in _TRUTHY


def _parse_number(raw: str) -> Any:
    """ISO d'abord, puis repli sur la notation FR ("1 234,56")."""
    for candidate in (raw, _normalize_french_number(raw)):
        result = _try_number(candidate)
        if result is not None:
            return result
    return raw


def _parse_temporal(raw: str, formats: tuple[str, ...], *, date_only: bool) -> Any:
    """ISO 8601 d'abord, puis les formats FR ; rend raw si aucun ne convient.

    Facteur commun a DATE et DATETIME, qui ne different que par la liste de
    formats de repli et par la troncature a la date.
    """
    candidate = raw.strip()
    try:
        parsed = datetime.fromisoformat(candidate)
    except (ValueError, TypeError):
        parsed = None
    if parsed is None:
        for fmt in formats:
            try:
                parsed = datetime.strptime(candidate, fmt)
                break
            except (ValueError, TypeError):
                continue
    if parsed is None:
        return raw
    return parsed.date().isoformat() if date_only else parsed.isoformat()


def _parse_date(raw: str) -> Any:
    return _parse_temporal(raw, _FRENCH_DATE_FORMATS, date_only=True)


def _parse_datetime(raw: str) -> Any:
    return _parse_temporal(raw, _FRENCH_DATETIME_FORMATS, date_only=False)


def _parse_text(raw: str) -> Any:
    return raw


#: Un parseur par FieldValueType. Une table de dispatch plutot qu'une chaine de
#: if : chaque type se lit isolement, et ajouter un type ne rallonge plus une
#: fonction unique que pylint finissait par refuser (14 returns, 15 branches).
_PARSERS = {
    FieldValueType.TEXT.value: _parse_text,
    FieldValueType.BOOLEAN.value: _parse_boolean,
    FieldValueType.NUMBER.value: _parse_number,
    FieldValueType.DATE.value: _parse_date,
    FieldValueType.DATETIME.value: _parse_datetime,
}


def parse_field_value(raw: Optional[str], value_type: Optional[str]) -> Any:
    """Convertit une valeur brute string selon son FieldValueType.

    Retourne la valeur convertie dans son type natif Python/JSON quand
    la conversion est possible, sinon retourne raw tel quel sans erreur.
    """
    if raw is None or value_type is None or not isinstance(raw, str):
        return raw
    parser = _PARSERS.get(value_type)
    return parser(raw) if parser is not None else raw
