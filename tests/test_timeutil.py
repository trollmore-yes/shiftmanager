from datetime import datetime
from zoneinfo import ZoneInfo

from shiftbot.timeutil import week_start, is_noon

TZ = ZoneInfo("America/Los_Angeles")


def test_week_start_sunday():
    # 2026-06-28 is a Sunday
    dt = datetime(2026, 6, 28, 14, 30, tzinfo=TZ)
    ws = week_start(dt)
    assert ws.weekday() == 6  # Sunday
    assert ws.hour == 0
    assert ws.minute == 0
    assert ws.day == 28


def test_week_start_wednesday():
    # 2026-07-01 is a Wednesday
    dt = datetime(2026, 7, 1, 10, 0, tzinfo=TZ)
    ws = week_start(dt)
    assert ws.day == 28  # Sunday June 28
    assert ws.month == 6


def test_week_start_saturday():
    # 2026-07-04 is a Saturday
    dt = datetime(2026, 7, 4, 23, 59, tzinfo=TZ)
    ws = week_start(dt)
    assert ws.day == 28  # Sunday June 28


def test_week_start_monday():
    # 2026-06-29 is Monday
    dt = datetime(2026, 6, 29, 8, 0, tzinfo=TZ)
    ws = week_start(dt)
    assert ws.day == 28


def test_is_noon():
    assert is_noon(datetime(2026, 7, 1, 12, 0, tzinfo=TZ))
    assert not is_noon(datetime(2026, 7, 1, 12, 1, tzinfo=TZ))
    assert not is_noon(datetime(2026, 7, 1, 11, 59, tzinfo=TZ))
    assert not is_noon(datetime(2026, 7, 1, 0, 0, tzinfo=TZ))
