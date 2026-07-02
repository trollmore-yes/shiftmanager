import os
from functools import cache
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()


@cache
def discord_token() -> str:
    return os.environ["DISCORD_TOKEN"]


def db_path() -> str:
    return os.environ.get("DB_PATH", "data/shiftbot.db")


def tz() -> ZoneInfo:
    return ZoneInfo(os.environ.get("TZ", "America/Los_Angeles"))


def log_level() -> str:
    return os.environ.get("LOG_LEVEL", "INFO")
