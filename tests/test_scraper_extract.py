from playwright.sync_api import sync_playwright
from src.scraper import extract_date_tables, SLOTS

# Header slot cells replicate the live site's actual markup: the time range
# is split across a child <span> (introducing whitespace/newlines around it
# when read via inner_text()) and uses U+FF5E FULLWIDTH TILDE ("～") rather
# than the U+301C WAVE DASH ("〜") that SLOTS uses. Both quirks must be
# normalized by extract_date_tables for slot_labels to match SLOTS exactly.
FIXTURE_HTML = """
<html><body>
<table>
  <thead>
    <tr>
      <th>2026年8月22日(土)</th>
      <th>定員</th>
      <th>9:00<span>～</span>11:00</th>
      <th>11:00<span>～</span>13:00</th>
      <th>13:00<span>～</span>15:00</th>
      <th>15:00<span>～</span>17:00</th>
      <th>17:00<span>～</span>18:00</th>
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
      <th>9:00<span>～</span>11:00</th>
      <th>11:00<span>～</span>13:00</th>
      <th>13:00<span>～</span>15:00</th>
      <th>15:00<span>～</span>17:00</th>
      <th>17:00<span>～</span>18:00</th>
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
      <th>9:00<span>～</span>11:00</th>
      <th>11:00<span>～</span>13:00</th>
      <th>13:00<span>～</span>15:00</th>
      <th>15:00<span>～</span>17:00</th>
      <th>17:00<span>～</span>18:00</th>
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
