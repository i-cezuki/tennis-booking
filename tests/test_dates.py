from datetime import date, datetime, timezone
from src import dates as dates_module
from src.dates import (
    weekend_dates_in_range,
    weekend_and_holiday_dates_in_range,
    parse_japanese_date,
    today_jst,
)


def test_weekend_dates_in_range_includes_only_sat_sun():
    # 2026-08-16 is a Sunday
    start = date(2026, 8, 16)
    result = weekend_dates_in_range(start, 14)
    assert all(d.weekday() in (5, 6) for d in result)


def test_weekend_dates_in_range_includes_start_if_weekend():
    start = date(2026, 8, 16)  # Sunday
    result = weekend_dates_in_range(start, 14)
    assert date(2026, 8, 16) in result


def test_weekend_dates_in_range_excludes_dates_outside_window():
    start = date(2026, 8, 16)
    result = weekend_dates_in_range(start, 14)
    assert all(start <= d < date(2026, 8, 30) for d in result)


def test_weekend_dates_in_range_sorted_ascending():
    start = date(2026, 8, 16)
    result = weekend_dates_in_range(start, 14)
    assert result == sorted(result)


def test_weekend_dates_in_range_exact_expected_set():
    start = date(2026, 8, 16)  # Sunday
    result = weekend_dates_in_range(start, 14)
    assert result == [
        date(2026, 8, 16),  # Sun
        date(2026, 8, 22),  # Sat
        date(2026, 8, 23),  # Sun
        date(2026, 8, 29),  # Sat
    ]


def test_weekend_and_holiday_dates_in_range_includes_weekday_holiday():
    # 2026-09-21 (Mon) is 敬老の日, a national holiday falling on a weekday --
    # weekend_dates_in_range alone would miss it entirely, silently never
    # checking court availability for it.
    start = date(2026, 9, 18)  # Fri
    result = weekend_and_holiday_dates_in_range(start, 14)
    assert date(2026, 9, 21) in result


def test_weekend_and_holiday_dates_in_range_includes_consecutive_weekday_holidays():
    # 2026-09-21/22/23 (Mon/Tue/Wed) are 敬老の日, 国民の休日, 秋分の日 --
    # three consecutive weekday holidays via the "citizens' holiday" bridge
    # rule, none of which are Saturday/Sunday.
    start = date(2026, 9, 18)
    result = weekend_and_holiday_dates_in_range(start, 14)
    assert date(2026, 9, 21) in result
    assert date(2026, 9, 22) in result
    assert date(2026, 9, 23) in result


def test_weekend_and_holiday_dates_in_range_still_includes_weekends():
    start = date(2026, 8, 16)  # Sunday
    result = weekend_and_holiday_dates_in_range(start, 14)
    assert date(2026, 8, 16) in result
    assert date(2026, 8, 22) in result


def test_weekend_and_holiday_dates_in_range_excludes_ordinary_weekdays():
    # 2026-09-24 (Thu) is an ordinary weekday, not a holiday.
    start = date(2026, 9, 18)
    result = weekend_and_holiday_dates_in_range(start, 14)
    assert date(2026, 9, 24) not in result


def test_weekend_and_holiday_dates_in_range_no_duplicate_when_holiday_is_weekend():
    # A holiday that also happens to fall on a Saturday/Sunday must not be
    # double-counted: 2026-05-03 (憲法記念日) is a Sunday.
    start = date(2026, 4, 27)
    result = weekend_and_holiday_dates_in_range(start, 14)
    assert result.count(date(2026, 5, 3)) == 1


def test_weekend_and_holiday_dates_in_range_sorted_ascending():
    start = date(2026, 9, 18)
    result = weekend_and_holiday_dates_in_range(start, 14)
    assert result == sorted(result)


def test_parse_japanese_date_basic():
    assert parse_japanese_date("2026年8月22日(土)") == date(2026, 8, 22)


def test_parse_japanese_date_single_digit_month_day():
    assert parse_japanese_date("2026年9月6日(日)") == date(2026, 9, 6)


def test_today_jst_uses_tokyo_date_not_utc_date(monkeypatch):
    # 2026-08-29 23:47 UTC is already 2026-08-30 08:47 JST: a UTC-based
    # "today" would be a full calendar day behind the site's actual today.
    utc_now = datetime(2026, 8, 29, 23, 47, tzinfo=timezone.utc)

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return utc_now.astimezone(tz) if tz else utc_now

    monkeypatch.setattr(dates_module, "datetime", FakeDateTime)

    assert today_jst() == date(2026, 8, 30)
