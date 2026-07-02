import re

UNIT_RE = re.compile(
    r"^(?:(?P<hours>\d+)\s*h(?:ours?)?)?\s*(?:(?P<minutes>\d+)\s*m(?:in(?:utes?)?)?)?$",
    re.IGNORECASE,
)
BARE_RE = re.compile(r"^\d+$")


def parse_duration(text: str) -> int:
    """Parse a human duration string into total minutes.

    Supported formats: "1h30m", "90m", "2h", "15", "1 hour 30 min".
    Bare numbers like "90" are treated as minutes.
    Returns total minutes. Raises ValueError if unparseable or zero.
    """
    text = text.strip()
    if BARE_RE.match(text):
        val = int(text)
        if val <= 0:
            raise ValueError(f"Duration must be > 0: {text!r}")
        return val
    m = UNIT_RE.match(text)
    if not m:
        raise ValueError(f"Could not parse duration: {text!r}")
    hours = int(m.group("hours")) if m.group("hours") else 0
    minutes = int(m.group("minutes")) if m.group("minutes") else 0
    if hours == 0 and minutes == 0:
        raise ValueError(f"Duration must be > 0: {text!r}")
    return hours * 60 + minutes
