import re
from datetime import date, timedelta

_JP_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")


def weekend_dates_in_range(start: date, num_days: int) -> list[date]:
    """Return every Saturday/Sunday in [start, start + num_days), sorted ascending."""
    result = []
    for offset in range(num_days):
        current = start + timedelta(days=offset)
        if current.weekday() in (5, 6):  # Saturday=5, Sunday=6
            result.append(current)
    return result


def parse_japanese_date(text: str) -> date:
    """Parse a Japanese date string like '2026年8月22日(土)' into a date object."""
    match = _JP_DATE_RE.search(text)
    if not match:
        raise ValueError(f"Could not parse Japanese date from: {text!r}")
    year, month, day = (int(g) for g in match.groups())
    return date(year, month, day)
