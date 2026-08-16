from datetime import date
from src.dates import weekend_dates_in_range, parse_japanese_date


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


def test_parse_japanese_date_basic():
    assert parse_japanese_date("2026年8月22日(土)") == date(2026, 8, 22)


def test_parse_japanese_date_single_digit_month_day():
    assert parse_japanese_date("2026年9月6日(日)") == date(2026, 9, 6)
