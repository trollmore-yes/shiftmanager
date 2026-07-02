from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def now(tz: ZoneInfo) -> datetime:
    return datetime.now(tz)


def week_start(dt: datetime) -> datetime:
    days_since_sunday = (dt.weekday() + 1) % 7
    return (dt - timedelta(days=days_since_sunday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def is_noon(dt: datetime) -> bool:
    return dt.hour == 12 and dt.minute == 0
