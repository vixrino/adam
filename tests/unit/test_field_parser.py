"""Tests unitaires pour adam_core.utils.field_parser."""

from adam_core.utils.field_parser import parse_field_value


# ---------------------------------------------------------------------------
# TEXT
# ---------------------------------------------------------------------------

def test_text_returns_raw() -> None:
    assert parse_field_value("hello", "text") == "hello"


def test_text_none_returns_none() -> None:
    assert parse_field_value(None, "text") is None


# ---------------------------------------------------------------------------
# NUMBER
# ---------------------------------------------------------------------------

def test_number_integer() -> None:
    assert parse_field_value("450000", "number") == 450000
    assert isinstance(parse_field_value("450000", "number"), int)


def test_number_small_integer() -> None:
    assert parse_field_value("85", "number") == 85


def test_number_float() -> None:
    assert parse_field_value("3.14", "number") == 3.14
    assert isinstance(parse_field_value("3.14", "number"), float)


def test_number_not_convertible_returns_raw() -> None:
    assert parse_field_value("12 BIS", "number") == "12 BIS"


def test_number_alphanumeric_returns_raw() -> None:
    assert parse_field_value("ABC123", "number") == "ABC123"


def test_number_none_returns_none() -> None:
    assert parse_field_value(None, "number") is None


def test_number_french_thousand_separator_space() -> None:
    assert parse_field_value("450 000", "number") == 450000
    assert isinstance(parse_field_value("450 000", "number"), int)


def test_number_french_decimal_comma() -> None:
    assert parse_field_value("12,5", "number") == 12.5


def test_number_french_thousand_dot_decimal_comma() -> None:
    assert parse_field_value("1.234,56", "number") == 1234.56


def test_number_french_thousand_space_decimal_comma() -> None:
    assert parse_field_value("1 234,56", "number") == 1234.56


def test_number_french_not_convertible_returns_raw() -> None:
    assert parse_field_value("12 BIS", "number") == "12 BIS"


def test_number_nan_returns_raw() -> None:
    assert parse_field_value("nan", "number") == "nan"


def test_number_infinity_returns_raw() -> None:
    assert parse_field_value("inf", "number") == "inf"


def test_number_negative_infinity_returns_raw() -> None:
    assert parse_field_value("-inf", "number") == "-inf"


# ---------------------------------------------------------------------------
# BOOLEAN
# ---------------------------------------------------------------------------

def test_boolean_true_lowercase() -> None:
    assert parse_field_value("true", "boolean") is True


def test_boolean_true_uppercase() -> None:
    assert parse_field_value("True", "boolean") is True


def test_boolean_one() -> None:
    assert parse_field_value("1", "boolean") is True


def test_boolean_false_lowercase() -> None:
    assert parse_field_value("false", "boolean") is False


def test_boolean_zero() -> None:
    assert parse_field_value("0", "boolean") is False


def test_boolean_unknown_string_is_false() -> None:
    assert parse_field_value("maybe", "boolean") is False


# ---------------------------------------------------------------------------
# DATE
# ---------------------------------------------------------------------------

def test_date_valid_iso() -> None:
    assert parse_field_value("2024-01-15", "date") == "2024-01-15"


def test_date_invalid_returns_raw() -> None:
    assert parse_field_value("not-a-date", "date") == "not-a-date"


def test_date_none_returns_none() -> None:
    assert parse_field_value(None, "date") is None


def test_date_french_slash_format() -> None:
    assert parse_field_value("20/06/2026", "date") == "2026-06-20"


def test_date_french_dash_format() -> None:
    assert parse_field_value("20-06-2026", "date") == "2026-06-20"


def test_date_french_dot_format() -> None:
    assert parse_field_value("20.06.2026", "date") == "2026-06-20"


def test_date_strips_surrounding_whitespace() -> None:
    assert parse_field_value(" 2024-01-15 ", "date") == "2024-01-15"


def test_date_french_strips_surrounding_whitespace() -> None:
    assert parse_field_value("  20/06/2026  ", "date") == "2026-06-20"


def test_date_french_space_separator() -> None:
    assert parse_field_value("20 06 2026", "date") == "2026-06-20"


# ---------------------------------------------------------------------------
# DATETIME
# ---------------------------------------------------------------------------

def test_datetime_valid_iso() -> None:
    result = parse_field_value("2024-01-15T10:30:00", "datetime")
    assert result == "2024-01-15T10:30:00"


def test_datetime_invalid_returns_raw() -> None:
    assert parse_field_value("not-a-datetime", "datetime") == "not-a-datetime"


def test_datetime_none_returns_none() -> None:
    assert parse_field_value(None, "datetime") is None


def test_datetime_french_slash_with_seconds() -> None:
    assert parse_field_value("20/06/2026 14:30:00", "datetime") == "2026-06-20T14:30:00"


def test_datetime_french_slash_without_seconds() -> None:
    assert parse_field_value("20/06/2026 14:30", "datetime") == "2026-06-20T14:30:00"


def test_datetime_french_dash_format() -> None:
    assert parse_field_value("20-06-2026 14:30", "datetime") == "2026-06-20T14:30:00"


def test_datetime_strips_surrounding_whitespace() -> None:
    assert parse_field_value("2024-01-15T10:30:00 ", "datetime") == "2024-01-15T10:30:00"


def test_datetime_z_suffix_normalized_to_offset() -> None:
    assert parse_field_value("2024-01-15T10:30:00Z", "datetime") == "2024-01-15T10:30:00+00:00"


def test_datetime_french_space_date_separator() -> None:
    assert parse_field_value("20 06 2026 14:30", "datetime") == "2026-06-20T14:30:00"


# ---------------------------------------------------------------------------
# Cas limites
# ---------------------------------------------------------------------------

def test_unknown_value_type_returns_raw() -> None:
    assert parse_field_value("foo", "UNKNOWN_TYPE") == "foo"


def test_none_value_type_returns_raw() -> None:
    assert parse_field_value("foo", None) == "foo"


def test_both_none_returns_none() -> None:
    assert parse_field_value(None, None) is None
