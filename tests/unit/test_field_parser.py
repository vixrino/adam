"""Tests unitaires pour adam_core.utils.field_parser."""

from adam_core.utils.field_parser import parse_field_value


# ---------------------------------------------------------------------------
# TEXT
# ---------------------------------------------------------------------------

def test_text_returns_raw() -> None:
    assert parse_field_value("hello", "TEXT") == "hello"


def test_text_none_returns_none() -> None:
    assert parse_field_value(None, "TEXT") is None


# ---------------------------------------------------------------------------
# NUMBER
# ---------------------------------------------------------------------------

def test_number_integer() -> None:
    assert parse_field_value("450000", "NUMBER") == 450000
    assert isinstance(parse_field_value("450000", "NUMBER"), int)


def test_number_small_integer() -> None:
    assert parse_field_value("85", "NUMBER") == 85


def test_number_float() -> None:
    assert parse_field_value("3.14", "NUMBER") == 3.14
    assert isinstance(parse_field_value("3.14", "NUMBER"), float)


def test_number_not_convertible_returns_raw() -> None:
    assert parse_field_value("12 BIS", "NUMBER") == "12 BIS"


def test_number_alphanumeric_returns_raw() -> None:
    assert parse_field_value("ABC123", "NUMBER") == "ABC123"


def test_number_none_returns_none() -> None:
    assert parse_field_value(None, "NUMBER") is None


# ---------------------------------------------------------------------------
# BOOLEAN
# ---------------------------------------------------------------------------

def test_boolean_true_lowercase() -> None:
    assert parse_field_value("true", "BOOLEAN") is True


def test_boolean_true_uppercase() -> None:
    assert parse_field_value("True", "BOOLEAN") is True


def test_boolean_one() -> None:
    assert parse_field_value("1", "BOOLEAN") is True


def test_boolean_false_lowercase() -> None:
    assert parse_field_value("false", "BOOLEAN") is False


def test_boolean_zero() -> None:
    assert parse_field_value("0", "BOOLEAN") is False


def test_boolean_unknown_string_is_false() -> None:
    assert parse_field_value("maybe", "BOOLEAN") is False


# ---------------------------------------------------------------------------
# DATE
# ---------------------------------------------------------------------------

def test_date_valid_iso() -> None:
    assert parse_field_value("2024-01-15", "DATE") == "2024-01-15"


def test_date_invalid_returns_raw() -> None:
    assert parse_field_value("not-a-date", "DATE") == "not-a-date"


def test_date_none_returns_none() -> None:
    assert parse_field_value(None, "DATE") is None


# ---------------------------------------------------------------------------
# DATETIME
# ---------------------------------------------------------------------------

def test_datetime_valid_iso() -> None:
    result = parse_field_value("2024-01-15T10:30:00", "DATETIME")
    assert result == "2024-01-15T10:30:00"


def test_datetime_invalid_returns_raw() -> None:
    assert parse_field_value("not-a-datetime", "DATETIME") == "not-a-datetime"


def test_datetime_none_returns_none() -> None:
    assert parse_field_value(None, "DATETIME") is None


# ---------------------------------------------------------------------------
# Cas limites
# ---------------------------------------------------------------------------

def test_unknown_value_type_returns_raw() -> None:
    assert parse_field_value("foo", "UNKNOWN_TYPE") == "foo"


def test_none_value_type_returns_raw() -> None:
    assert parse_field_value("foo", None) == "foo"


def test_both_none_returns_none() -> None:
    assert parse_field_value(None, None) is None
