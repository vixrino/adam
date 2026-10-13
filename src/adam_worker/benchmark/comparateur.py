"""Comparaison d'une valeur lue par le moteur a la verite terrain.

Fonctions pures : aucune base, aucun reseau. Le worker de benchmark les appelle
champ par champ, et seuls les ecarts qu'elles signalent sont ecrits.

Comparaison normalisee
----------------------
Un ecart doit mesurer une erreur de lecture, pas une difference de forme :
    TEXT      casse, accents et espaces ignores (« Mme  THÉRY » = « mme thery »)
    NUMBER    par valeur (« 1 738,26 » = « 1738.26 »)
    DATE      par date (« 17/09/1969 » = « 17/09/69 » = « 1969-09-17 »)
    BOOLEAN   par valeur (« true » = « oui »)

Verdicts
--------
    MISSING   la verite porte une valeur, le moteur n'a rien rendu
    WRONG     le moteur a rendu autre chose que la verite — y compris une
              valeur la ou la verite est vide : un champ invente est une erreur

Confidentialite
---------------
Pour un champ sensible, ni la valeur attendue ni la valeur lue ne sortent d'ici :
seuls un HMAC a cle de la valeur lue (pour reconnaitre une erreur recurrente),
la distance d'edition (son ampleur) et la categorie de l'ecart sont rendus.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from adam_core.enums.status import ComparisonDiffKind, ComparisonVerdict, FieldValueType
from adam_core.utils.field_parser import parse_field_value

#: Version de la regle de comparaison (normalisation, verdicts, matrice). A
#: incrementer a chaque changement : deux executions dont la version differe ne
#: se comparent pas, un meme moteur pouvant y gagner ou perdre des points.
COMPARATEUR_VERSION = "1"

#: Tolerance sur les nombres : deux montants lus « 1738.26 » et « 1738.2600001 »
#: sont la meme lecture.
_TOLERANCE = 1e-6


@dataclass(frozen=True)
class Ecart:
    """Un ecart entre lecture et verite, pret a devenir un comparison_result."""

    verdict: ComparisonVerdict
    diff_kind: Optional[ComparisonDiffKind]
    #: Valeurs brutes, a ne stocker que pour un champ non sensible.
    attendu: Optional[str]
    lu: Optional[str]
    edit_distance: Optional[int]


def _texte(valeur: str) -> str:
    """Minuscules, sans accents, espaces fusionnes."""
    sans_accents = "".join(
        c for c in unicodedata.normalize("NFKD", valeur) if not unicodedata.combining(c)
    )
    return " ".join(sans_accents.lower().split())


def _date(valeur: str) -> Any:
    parsee = parse_field_value(valeur, FieldValueType.DATE.value)
    if parsee != valeur:
        return parsee
    # Annee a deux chiffres (« 17/09/69 ») : field_parser ne la lit pas.
    for format_ in ("%d/%m/%y", "%d-%m-%y", "%d.%m.%y"):
        try:
            return datetime.strptime(valeur.strip(), format_).date().isoformat()
        except ValueError:
            continue
    return _texte(valeur)


def normaliser(valeur: Optional[str], value_type: Optional[str]) -> Any:
    """Forme comparable d'une valeur ; None pour une valeur absente ou vide."""
    if valeur is None or not str(valeur).strip():
        return None
    brut = str(valeur).strip()
    type_ = (value_type or FieldValueType.TEXT.value).upper()
    if type_ in (FieldValueType.DATE.value, FieldValueType.DATETIME.value):
        return _date(brut)
    if type_ in (FieldValueType.NUMBER.value, FieldValueType.BOOLEAN.value):
        parsee = parse_field_value(brut, type_)
        return parsee if parsee != brut else _texte(brut)
    return _texte(brut)


def _egaux(attendu: Any, lu: Any) -> bool:
    if isinstance(attendu, bool) or isinstance(lu, bool):
        return attendu == lu
    if isinstance(attendu, (int, float)) and isinstance(lu, (int, float)):
        return abs(float(attendu) - float(lu)) <= _TOLERANCE
    return bool(attendu == lu)


def distance_edition(a: str, b: str) -> int:
    """Distance de Levenshtein, en O(len(a) * len(b)) — des valeurs de champ."""
    if len(a) < len(b):
        a, b = b, a
    precedente = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        courante = [i]
        for j, cb in enumerate(b, start=1):
            courante.append(
                min(precedente[j] + 1, courante[j - 1] + 1, precedente[j - 1] + (ca != cb))
            )
        precedente = courante
    return precedente[-1]


def categorie(attendu: str, lu: str) -> ComparisonDiffKind:
    """Nature d'un ecart WRONG, publiable meme pour un champ sensible."""
    if attendu.lower() == lu.lower():
        return ComparisonDiffKind.CASE
    if attendu.split() == lu.split() or "".join(attendu.split()) == "".join(lu.split()):
        return ComparisonDiffKind.WHITESPACE
    alnum_attendu = re.sub(r"[^0-9a-z]", "", _texte(attendu))
    alnum_lu = re.sub(r"[^0-9a-z]", "", _texte(lu))
    if alnum_attendu == alnum_lu:
        # Memes lettres et chiffres, ponctuation ou separateurs differents.
        return ComparisonDiffKind.FORMAT
    chiffres_attendu = re.sub(r"\D", "", attendu)
    if chiffres_attendu and len(chiffres_attendu) == len(re.sub(r"\D", "", lu)):
        if re.sub(r"\d", "", alnum_attendu) == re.sub(r"\d", "", alnum_lu):
            # Seuls des chiffres different : le moteur lit mal les chiffres.
            return ComparisonDiffKind.DIGIT
    return ComparisonDiffKind.TOTAL


def comparer(
    attendu: Optional[str], lu: Optional[str], value_type: Optional[str]
) -> Optional[Ecart]:
    """L'ecart entre la verite et la lecture, ou None si elles concordent."""
    forme_attendue = normaliser(attendu, value_type)
    forme_lue = normaliser(lu, value_type)
    if forme_attendue is None and forme_lue is None:
        return None
    if forme_attendue is not None and forme_lue is None:
        return Ecart(ComparisonVerdict.MISSING, None, attendu, None, None)
    if forme_attendue is not None and _egaux(forme_attendue, forme_lue):
        return None
    texte_attendu = str(attendu or "").strip()
    texte_lu = str(lu or "").strip()
    return Ecart(
        verdict=ComparisonVerdict.WRONG,
        diff_kind=categorie(texte_attendu, texte_lu) if texte_attendu else ComparisonDiffKind.TOTAL,
        attendu=attendu,
        lu=lu,
        edit_distance=distance_edition(_texte(texte_attendu), _texte(texte_lu)),
    )


def empreinte(valeur: Optional[str], cle: str) -> Optional[str]:
    """HMAC-SHA256 de la valeur lue, normalisee : deux lectures identiques d'un
    meme IBAN donnent la meme empreinte, sans que l'IBAN soit stocke."""
    if valeur is None or not cle:
        return None
    return hmac.new(cle.encode(), _texte(str(valeur)).encode(), hashlib.sha256).hexdigest()
