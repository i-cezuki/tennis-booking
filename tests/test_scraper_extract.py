from playwright.sync_api import sync_playwright
from src.scraper import extract_date_tables

FIXTURE_HTML = """
<html><body>
<table>
  <thead>
    <tr>
      <th>2026年8月22日(土)</th>
      <th>定員</th>
      <th>9:00〜11:00</th>
      <th>11:00〜13:00</th>
      <th>13:00〜15:00</th>
      <th>15:00〜17:00</th>
      <th>17:00〜18:00</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>A面</td>
      <td>－</td>
      <td><input type="checkbox" aria-label="×"></td>
      <td><input type="checkbox" aria-label="○"></td>
      <td><input type="checkbox" aria-label="×"></td>
      <td><input type="checkbox" aria-label="×"></td>
      <td><input type="checkbox" aria-label="×"></td>
    </tr>
    <tr>
      <td>B面</td>
      <td>－</td>
      <td><input type="checkbox" aria-label="×"></td>
      <td><input type="checkbox" aria-label="×"></td>
      <td><input type="checkbox" aria-label="×"></td>
      <td><input type="checkbox" aria-label="×"></td>
      <td><input type="checkbox" aria-label="×"></td>
    </tr>
    <tr>
      <td>C面</td>
      <td>－</td>
      <td><input type="checkbox" aria-label="×"></td>
      <td><input type="checkbox" aria-label="×"></td>
      <td><input type="checkbox" aria-label="×"></td>
      <td><input type="checkbox" aria-label="×"></td>
      <td><input type="checkbox" aria-label="×"></td>
    </tr>
    <tr>
      <td>D面兼ゲートボール場</td>
      <td>－</td>
      <td><input type="checkbox" aria-label="×"></td>
      <td><input type="checkbox" aria-label="×"></td>
      <td><input type="checkbox" aria-label="×"></td>
      <td><input type="checkbox" aria-label="×"></td>
      <td><input type="checkbox" aria-label="×"></td>
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
