from datetime import date

import pytest
from playwright.sync_api import sync_playwright
from src.scraper import extract_date_tables, validate_extraction_result, SLOTS

# Header slot cells replicate the two live-site quirks that corrupt naively
# extracted slot labels: (1) the time range renders across rendered line
# breaks around the dash (plain inline <span> with no CSS does NOT insert
# newlines into Chromium's inner_text() -- the <br> tags here are what
# actually reproduce the real embedded-newline symptom, verified by
# confirming the pre-fix code fails against this fixture, see fix report 3),
# and (2) the dash itself is U+FF5E FULLWIDTH TILDE ("～"), not the
# U+301C WAVE DASH ("〜") that SLOTS uses. Both quirks must be normalized by
# extract_date_tables for slot_labels to match SLOTS exactly.
FIXTURE_HTML = """
<html><body>
<table>
  <thead>
    <tr>
      <th>2026年8月22日(土)</th>
      <th>定員</th>
      <th>9:00<br><span>～</span><br>11:00</th>
      <th>11:00<br><span>～</span><br>13:00</th>
      <th>13:00<br><span>～</span><br>15:00</th>
      <th>15:00<br><span>～</span><br>17:00</th>
      <th>17:00<br><span>～</span><br>18:00</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>A面</td>
      <td>－</td>
      <td><label>×</label></td>
      <td><input type="checkbox"><label>○</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
    </tr>
    <tr>
      <td>B面</td>
      <td>－</td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
    </tr>
    <tr>
      <td>C面</td>
      <td>－</td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
    </tr>
    <tr>
      <td>D面兼ゲートボール場</td>
      <td>－</td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
    </tr>
  </tbody>
</table>
</body></html>
"""


def test_extract_date_tables_parses_fixture():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(FIXTURE_HTML)

        result = extract_date_tables(page)

        browser.close()

    assert set(result.keys()) == {"2026-08-22"}
    day = result["2026-08-22"]
    assert set(day.keys()) == {"A面", "B面", "C面", "D面兼ゲートボール場"}
    assert day["A面"] == {
        "9:00〜11:00": "×",
        "11:00〜13:00": "○",
        "13:00〜15:00": "×",
        "15:00〜17:00": "×",
        "17:00〜18:00": "×",
    }
    assert day["B面"]["9:00〜11:00"] == "×"

    # Regression test: slot labels must exactly match SLOTS, with no
    # whitespace/newlines left over from the split <span> markup and no
    # leftover fullwidth tilde (U+FF5E) in place of the wave dash (U+301C).
    assert set(day["A面"].keys()) == set(SLOTS)
    for label in day["A面"]:
        assert "\n" not in label and " " not in label
        assert "～" not in label  # U+FF5E FULLWIDTH TILDE must not remain


FIXTURE_HTML_MULTI_TABLE = """
<html><body>
<table>
  <thead>
    <tr>
      <th>2026年8月22日(土)</th>
      <th>定員</th>
      <th>9:00<br><span>～</span><br>11:00</th>
      <th>11:00<br><span>～</span><br>13:00</th>
      <th>13:00<br><span>～</span><br>15:00</th>
      <th>15:00<br><span>～</span><br>17:00</th>
      <th>17:00<br><span>～</span><br>18:00</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>A面</td>
      <td>－</td>
      <td><label>×</label></td>
      <td><input type="checkbox"><label>○</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
    </tr>
    <tr>
      <td>B面</td>
      <td>－</td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
    </tr>
    <tr>
      <td>C面</td>
      <td>－</td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
    </tr>
    <tr>
      <td>D面兼ゲートボール場</td>
      <td>－</td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
    </tr>
  </tbody>
</table>

<table>
  <thead>
    <tr>
      <th>2026年8月23日(日)</th>
      <th>定員</th>
      <th>9:00<br><span>～</span><br>11:00</th>
      <th>11:00<br><span>～</span><br>13:00</th>
      <th>13:00<br><span>～</span><br>15:00</th>
      <th>15:00<br><span>～</span><br>17:00</th>
      <th>17:00<br><span>～</span><br>18:00</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>A面</td>
      <td>－</td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><input type="checkbox"><label>○</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
    </tr>
    <tr>
      <td>B面</td>
      <td>－</td>
      <td><label>×</label></td>
      <td><input type="checkbox"><label>○</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
    </tr>
    <tr>
      <td>C面</td>
      <td>－</td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
    </tr>
    <tr>
      <td>D面兼ゲートボール場</td>
      <td>－</td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
      <td><label>×</label></td>
    </tr>
  </tbody>
</table>
</body></html>
"""


def test_extract_date_tables_parses_multiple_tables():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(FIXTURE_HTML_MULTI_TABLE)

        result = extract_date_tables(page)

        browser.close()

    # Verify both dates are present as top-level keys
    assert set(result.keys()) == {"2026-08-22", "2026-08-23"}

    # Verify first date's data
    day_22 = result["2026-08-22"]
    assert set(day_22.keys()) == {"A面", "B面", "C面", "D面兼ゲートボール場"}
    assert day_22["A面"]["11:00〜13:00"] == "○"  # Distinguishing symbol for Aug 22
    assert day_22["B面"]["9:00〜11:00"] == "×"

    # Verify second date's data is different and not mixed up
    day_23 = result["2026-08-23"]
    assert set(day_23.keys()) == {"A面", "B面", "C面", "D面兼ゲートボール場"}
    assert day_23["A面"]["13:00〜15:00"] == "○"  # Different slot for Aug 23
    assert day_23["B面"]["11:00〜13:00"] == "○"  # Different slot for Aug 23
    assert day_23["B面"]["9:00〜11:00"] == "×"

    # Regression test: slot labels must exactly match SLOTS in both tables,
    # with no whitespace/newlines or leftover fullwidth tilde.
    for day in (day_22, day_23):
        for court_slots in day.values():
            assert set(court_slots.keys()) == set(SLOTS)
            for label in court_slots:
                assert "\n" not in label and " " not in label
                assert "～" not in label


def test_validate_extraction_result_raises_on_empty_result():
    # Simulates navigation silently landing on an unexpected page: no
    # tables found, extract_date_tables returns {}. This must raise
    # rather than let main() overwrite state.json with an empty snapshot.
    with pytest.raises(RuntimeError):
        validate_extraction_result({}, [date(2026, 8, 22), date(2026, 8, 23)])


def test_validate_extraction_result_raises_on_partial_result():
    # Simulates only some of the requested date tables being found (e.g.
    # a partial layout change) -- still a fail-loud condition.
    with pytest.raises(RuntimeError):
        validate_extraction_result(
            {"2026-08-22": {}}, [date(2026, 8, 22), date(2026, 8, 23)]
        )


def test_validate_extraction_result_passes_when_all_dates_present():
    # No exception when every requested date has an entry, regardless of
    # the per-date contents (that's extract_date_tables's concern).
    validate_extraction_result(
        {"2026-08-22": {}, "2026-08-23": {}},
        [date(2026, 8, 22), date(2026, 8, 23)],
    )
