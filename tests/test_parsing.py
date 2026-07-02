import pytest
from shiftbot.parsing import parse_duration


def test_hours_and_minutes():
    assert parse_duration("1h30m") == 90
    assert parse_duration("2h") == 120
    assert parse_duration("45m") == 45
    assert parse_duration("0h15m") == 15


def test_bare_number_is_minutes():
    assert parse_duration("90") == 90
    assert parse_duration("5") == 5


def test_variations():
    assert parse_duration("1 h 30 m") == 90
    assert parse_duration("2 hour") == 120
    assert parse_duration("30 min") == 30
    assert parse_duration("1h") == 60


def test_invalid():
    with pytest.raises(ValueError):
        parse_duration("")
    with pytest.raises(ValueError):
        parse_duration("0")
    with pytest.raises(ValueError):
        parse_duration("abc")
    with pytest.raises(ValueError):
        parse_duration("1x30")
