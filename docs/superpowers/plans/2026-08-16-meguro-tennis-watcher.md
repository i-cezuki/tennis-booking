# Meguro Tennis Court Cancellation Watcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect newly-opened cancellation slots on 目黒区施設予約システム for 駒場体育館 > 駒場庭球場 (weekends only, next 2 weeks) every 5 minutes via GitHub Actions, and notify Discord.

**Architecture:** A Python script (`src/main.py`) launches a headless Playwright browser, navigates the public (no-login) availability pages, extracts a `{date: {court: {slot: symbol}}}` snapshot, diffs it against the previously committed `state.json`, posts a Discord webhook message for any cell that newly became `○`, and writes the new snapshot back to `state.json`. A GitHub Actions workflow runs this every 5 minutes and commits `state.json` only when it changed.

**Tech Stack:** Python 3, Playwright (sync API, headless Chromium), `requests` for the Discord webhook, `pytest` for tests, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-16-meguro-tennis-watcher-design.md`

## Global Constraints

- Target: 駒場体育館 > 駒場庭球場, courts A面/B面/C面/D面兼ゲートボール場 (all 4), Saturdays and Sundays only, from today through the next 14 days inclusive.
- Time slots (exact labels, in this order): `9:00〜11:00`, `11:00〜13:00`, `13:00〜15:00`, `15:00〜17:00`, `17:00〜18:00`.
- No login — only pages reachable without authentication are used in v1.
- Language/runtime: Python + Playwright (headless Chromium).
- Schedule: GitHub Actions `schedule` trigger, `cron: '*/5 * * * *'`, plus `workflow_dispatch` for manual runs. Workflow needs `permissions: contents: write`.
- `state.json` lives in the repo root and is committed **only when its content changes** (not every run).
- Discord webhook URL is read from the `DISCORD_WEBHOOK_URL` GitHub Actions secret / environment variable — never hardcoded.
- On any unhandled error, log it and `exit(1)`; no Discord failure notifications in v1.
- `－` (申込対象外) cells are never openings and are ignored by the diff logic in both old and new state.

---

## File Structure

```
tennis-booking/
├── .github/workflows/watch.yml
├── requirements.txt
├── .gitignore
├── state.json
├── src/
│   ├── dates.py       # weekend date range calc + Japanese date parsing
│   ├── state.py        # load/save state.json
│   ├── diff.py          # new-openings detection (pure)
│   ├── notify.py        # Discord message building + sending
│   ├── scraper.py       # Playwright navigation + table extraction
│   └── main.py           # orchestration entry point
└── tests/
    ├── test_dates.py
    ├── test_state.py
    ├── test_diff.py
    ├── test_notify.py
    ├── test_scraper_extract.py
    └── test_main.py
```

---

### Task 1: Project scaffolding + date range calculation

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `src/__init__.py` (empty)
- Create: `src/dates.py`
- Test: `tests/test_dates.py`

**Interfaces:**
- Produces: `weekend_dates_in_range(start: date, num_days: int) -> list[date]`
- Produces: `parse_japanese_date(text: str) -> date` (parses strings like `"2026年8月22日(土)"` into `date(2026, 8, 22)`)

- [ ] **Step 1: Scaffolding**

Create `requirements.txt`:
```
playwright==1.47.0
requests==2.32.3
pytest==8.3.3
```

Create `.gitignore`:
```
__pycache__/
*.pyc
.pytest_cache/
venv/
.venv/
```

Create empty `src/__init__.py`.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_dates.py`:
```python
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/katsushifujiyoshi/github/tennis-booking && python -m pytest tests/test_dates.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.dates'` (or similar import error)

- [ ] **Step 4: Implement**

Create `src/dates.py`:
```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/katsushifujiyoshi/github/tennis-booking && python -m pytest tests/test_dates.py -v`
Expected: PASS (7 passed)

- [ ] **Step 6: Commit**

```bash
cd /Users/katsushifujiyoshi/github/tennis-booking
git add requirements.txt .gitignore src/__init__.py src/dates.py tests/test_dates.py
git commit -m "feat: add weekend date range calculation and Japanese date parsing"
```

---

### Task 2: State persistence (state.json read/write)

**Files:**
- Create: `src/state.py`
- Create: `state.json` (initial content `{}`)
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: nothing from other tasks
- Produces: `load_state(path: str) -> dict`, `save_state(path: str, data: dict) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_state.py`:
```python
import json
from src.state import load_state, save_state


def test_load_state_missing_file_returns_empty_dict(tmp_path):
    path = tmp_path / "does_not_exist.json"
    assert load_state(str(path)) == {}


def test_load_state_reads_existing_file(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}))
    assert load_state(str(path)) == {"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}


def test_save_state_writes_readable_json(tmp_path):
    path = tmp_path / "state.json"
    data = {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}
    save_state(str(path), data)
    assert json.loads(path.read_text()) == data


def test_save_state_output_ends_with_newline(tmp_path):
    path = tmp_path / "state.json"
    save_state(str(path), {"a": 1})
    assert path.read_text().endswith("\n")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/katsushifujiyoshi/github/tennis-booking && python -m pytest tests/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.state'`

- [ ] **Step 3: Implement**

Create `src/state.py`:
```python
import json
import os


def load_state(path: str) -> dict:
    """Return the parsed JSON at `path`, or {} if the file does not exist."""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(path: str, data: dict) -> None:
    """Write `data` to `path` as sorted, indented JSON with a trailing newline."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
```

Create `state.json` at repo root with content:
```json
{}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/katsushifujiyoshi/github/tennis-booking && python -m pytest tests/test_state.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
cd /Users/katsushifujiyoshi/github/tennis-booking
git add src/state.py state.json tests/test_state.py
git commit -m "feat: add state.json load/save helpers"
```

---

### Task 3: New-openings diff logic

**Files:**
- Create: `src/diff.py`
- Test: `tests/test_diff.py`

**Interfaces:**
- Consumes: state dicts shaped `{date_str: {court: {slot: symbol}}}` (symbol is one of `"○"`, `"×"`, `"－"`), as produced by `src.state.load_state` / `src.scraper.fetch_availability`
- Produces: `find_new_openings(old_state: dict, new_state: dict) -> list[dict]`, each item shaped `{"date": str, "court": str, "slot": str}`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_diff.py`:
```python
from src.diff import find_new_openings


def test_detects_transition_from_x_to_maru():
    old = {"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}
    new = {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}
    assert find_new_openings(old, new) == [
        {"date": "2026-08-22", "court": "A面", "slot": "9:00〜11:00"}
    ]


def test_detects_opening_with_no_prior_record():
    old = {}
    new = {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}
    assert find_new_openings(old, new) == [
        {"date": "2026-08-22", "court": "A面", "slot": "9:00〜11:00"}
    ]


def test_no_change_when_still_x():
    old = {"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}
    new = {"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}
    assert find_new_openings(old, new) == []


def test_no_duplicate_when_already_open():
    old = {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}
    new = {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}
    assert find_new_openings(old, new) == []


def test_ignores_moushikomi_taishougai():
    old = {"2026-08-22": {"A面": {"9:00〜11:00": "－"}}}
    new = {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}
    assert find_new_openings(old, new) == []


def test_handles_multiple_dates_and_courts():
    old = {
        "2026-08-22": {"A面": {"9:00〜11:00": "×"}, "B面": {"9:00〜11:00": "×"}},
        "2026-08-23": {"A面": {"9:00〜11:00": "×"}},
    }
    new = {
        "2026-08-22": {"A面": {"9:00〜11:00": "○"}, "B面": {"9:00〜11:00": "×"}},
        "2026-08-23": {"A面": {"9:00〜11:00": "○"}},
    }
    result = find_new_openings(old, new)
    assert {"date": "2026-08-22", "court": "A面", "slot": "9:00〜11:00"} in result
    assert {"date": "2026-08-23", "court": "A面", "slot": "9:00〜11:00"} in result
    assert len(result) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/katsushifujiyoshi/github/tennis-booking && python -m pytest tests/test_diff.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.diff'`

- [ ] **Step 3: Implement**

Create `src/diff.py`:
```python
def find_new_openings(old_state: dict, new_state: dict) -> list[dict]:
    """Return cells that are '○' in new_state but were not '○' in old_state.

    '－' (not applicable) cells never produce an opening, regardless of
    what they transitioned from or to.
    """
    openings = []
    for date_str, courts in new_state.items():
        for court, slots in courts.items():
            for slot, symbol in slots.items():
                if symbol != "○":
                    continue
                old_symbol = (
                    old_state.get(date_str, {}).get(court, {}).get(slot)
                )
                if old_symbol != "○":
                    openings.append({"date": date_str, "court": court, "slot": slot})
    return openings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/katsushifujiyoshi/github/tennis-booking && python -m pytest tests/test_diff.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
cd /Users/katsushifujiyoshi/github/tennis-booking
git add src/diff.py tests/test_diff.py
git commit -m "feat: add new-openings diff logic"
```

---

### Task 4: Discord notification

**Files:**
- Create: `src/notify.py`
- Test: `tests/test_notify.py`

**Interfaces:**
- Consumes: `list[dict]` of openings shaped `{"date": str, "court": str, "slot": str}` (from `src.diff.find_new_openings`)
- Produces: `build_message(openings: list[dict]) -> str`, `send_discord_notification(webhook_url: str, message: str) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_notify.py`:
```python
import pytest
from src.notify import build_message, send_discord_notification


def test_build_message_includes_date_court_slot():
    openings = [{"date": "2026-08-22", "court": "A面", "slot": "9:00〜11:00"}]
    message = build_message(openings)
    assert "2026-08-22" in message
    assert "A面" in message
    assert "9:00〜11:00" in message


def test_build_message_includes_reservation_url():
    openings = [{"date": "2026-08-22", "court": "A面", "slot": "9:00〜11:00"}]
    message = build_message(openings)
    assert "https://resv.city.meguro.tokyo.jp/Web/" in message


def test_build_message_lists_multiple_openings():
    openings = [
        {"date": "2026-08-22", "court": "A面", "slot": "9:00〜11:00"},
        {"date": "2026-08-23", "court": "B面", "slot": "11:00〜13:00"},
    ]
    message = build_message(openings)
    assert "2026-08-22" in message
    assert "2026-08-23" in message
    assert "A面" in message
    assert "B面" in message


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_send_discord_notification_posts_content(monkeypatch):
    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(204)

    monkeypatch.setattr("src.notify.requests.post", fake_post)
    send_discord_notification("https://discord.example/webhook", "hello")
    assert captured["url"] == "https://discord.example/webhook"
    assert captured["json"] == {"content": "hello"}


def test_send_discord_notification_raises_on_error_status(monkeypatch):
    def fake_post(url, json, timeout):
        return _FakeResponse(500)

    monkeypatch.setattr("src.notify.requests.post", fake_post)
    with pytest.raises(RuntimeError):
        send_discord_notification("https://discord.example/webhook", "hello")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/katsushifujiyoshi/github/tennis-booking && python -m pytest tests/test_notify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.notify'`

- [ ] **Step 3: Implement**

Create `src/notify.py`:
```python
import requests

TOP_PAGE_URL = "https://resv.city.meguro.tokyo.jp/Web/"


def build_message(openings: list[dict]) -> str:
    """Build a Discord message listing each new opening."""
    lines = ["駒場庭球場に新しい空きが見つかりました:"]
    for opening in openings:
        lines.append(
            f"- {opening['date']} {opening['court']} {opening['slot']}"
        )
    lines.append("")
    lines.append(f"予約サイト（トップ→スポーツ施設→駒場体育館）: {TOP_PAGE_URL}")
    return "\n".join(lines)


def send_discord_notification(webhook_url: str, message: str) -> None:
    """POST `message` to the Discord webhook URL. Raises on non-2xx response."""
    response = requests.post(webhook_url, json={"content": message}, timeout=10)
    response.raise_for_status()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/katsushifujiyoshi/github/tennis-booking && python -m pytest tests/test_notify.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
cd /Users/katsushifujiyoshi/github/tennis-booking
git add src/notify.py tests/test_notify.py
git commit -m "feat: add Discord notification message building and sending"
```

---

### Task 5: Availability table extraction (Playwright DOM parsing)

**Files:**
- Create: `src/scraper.py` (extraction function only in this task; navigation added in Task 6)
- Test: `tests/test_scraper_extract.py`

**Interfaces:**
- Consumes: a live Playwright `Page` object whose loaded content contains one or more 時間帯別空き状況-style tables; `parse_japanese_date` from `src.dates`
- Produces: `COURTS: list[str]`, `SLOTS: list[str]`, `extract_date_tables(page) -> dict` shaped `{date_str: {court: {slot: symbol}}}` with `date_str` as ISO (`YYYY-MM-DD`)

This mirrors the real page structure verified manually on 2026-08-16: each date has its own
`<table>` whose first header cell's accessible name is the Japanese date (e.g.
`"2026年8月22日(土)"`), second header is `定員`, remaining headers are the 5 time slot
labels. Each data row's first cell is the court name; each slot cell contains a checkbox
whose accessible name is the symbol (`○`/`×`/`－`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_scraper_extract.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/katsushifujiyoshi/github/tennis-booking && python -m playwright install chromium && python -m pytest tests/test_scraper_extract.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.scraper'`

- [ ] **Step 3: Implement**

Create `src/scraper.py`:
```python
from src.dates import parse_japanese_date

COURTS = ["A面", "B面", "C面", "D面兼ゲートボール場"]
SLOTS = ["9:00〜11:00", "11:00〜13:00", "13:00〜15:00", "15:00〜17:00", "17:00〜18:00"]


def extract_date_tables(page) -> dict:
    """Parse every date-block table currently on `page` into
    {iso_date: {court: {slot: symbol}}}.
    """
    result = {}
    tables = page.get_by_role("table").all()

    for table in tables:
        header_cells = table.get_by_role("columnheader").all()
        if not header_cells:
            continue

        date_text = header_cells[0].inner_text().strip()
        iso_date = parse_japanese_date(date_text).isoformat()
        slot_labels = [cell.inner_text().strip() for cell in header_cells[2:]]

        rows = table.get_by_role("row").all()
        day_data = {}
        for row in rows[1:]:  # skip header row
            cells = row.get_by_role("cell").all()
            if not cells:
                continue
            court_name = cells[0].inner_text().strip()
            if court_name not in COURTS:
                continue

            checkboxes = row.get_by_role("checkbox").all()
            slot_values = {}
            for slot_label, checkbox in zip(slot_labels, checkboxes):
                symbol = checkbox.get_attribute("aria-label")
                slot_values[slot_label] = symbol
            day_data[court_name] = slot_values

        result[iso_date] = day_data

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/katsushifujiyoshi/github/tennis-booking && python -m pytest tests/test_scraper_extract.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
cd /Users/katsushifujiyoshi/github/tennis-booking
git add src/scraper.py tests/test_scraper_extract.py
git commit -m "feat: add availability table extraction from Playwright page"
```

---

### Task 6: Live site navigation

**Files:**
- Modify: `src/scraper.py` (add navigation + top-level fetch function)

**Interfaces:**
- Consumes: `extract_date_tables` (this task, from Task 5), `date` objects from `src.dates.weekend_dates_in_range`
- Produces: `navigate_to_availability_page(page, target_dates: list[date]) -> None`, `fetch_availability(target_dates: list[date]) -> dict`

This task automates the exact flow manually verified against the live site on 2026-08-16:
top page → クリック「スポーツ施設」→ チェック「駒場体育館」→「次へ進む」→ 施設別空き状況で
表示期間を「2週間」にして「表示」→「駒場庭球場」行の対象日付（土日）をチェック→「次へ進む」
→ 時間帯別空き状況ページ。No automated test is written for this function — the spec
records the navigation as manually verified via live Playwright exploration, and this flow
is exercised via the manual smoke test in Step 2 below instead of a mocked unit test, since
faithfully mocking a multi-page ASP.NET WebForms postback flow would test the mock, not the
site.

- [ ] **Step 1: Implement**

Add to `src/scraper.py` (append below existing code). The column-to-date mapping is read
from the 施設別空き状況 table's `columnheader` cells (each showing day-of-month and weekday,
e.g. `"22 土"`), matched against `target_dates` by day-of-month, before checking the checkbox
in the `駒場庭球場` row at that column index:

```python
from datetime import date

TOP_PAGE_URL = "https://resv.city.meguro.tokyo.jp/Web/"
FACILITY_NAME = "駒場体育館"
COURT_ROW_NAME = "駒場庭球場"


def navigate_to_availability_page(page, target_dates: list[date]) -> None:
    """Drive `page` from the top page to the 時間帯別空き状況 page with
    `target_dates` selected for 駒場庭球場. After this call, page.content()
    contains the date-block tables that extract_date_tables() expects.
    """
    page.goto(TOP_PAGE_URL)
    page.get_by_role("button", name="スポーツ施設").click()
    page.get_by_role("cell", name=FACILITY_NAME).click()
    page.get_by_role("link", name="次へ進む").click()

    # 施設別空き状況: show a 2-week window starting today so all target
    # dates are visible in one grid.
    page.get_by_role("radio", name="2週間").check()
    page.get_by_role("button", name="表示").click()

    header_cells = page.get_by_role("columnheader").all()
    target_days = {d.day for d in target_dates}
    matching_columns = [
        i for i, cell in enumerate(header_cells)
        if any(str(day) == cell.inner_text().strip().split()[0] for day in target_days)
    ]

    court_row = page.get_by_role("row").filter(
        has=page.get_by_role("cell", name=COURT_ROW_NAME)
    )
    row_cells = court_row.get_by_role("cell").all()
    for col_index in matching_columns:
        checkbox = row_cells[col_index].get_by_role("checkbox")
        if checkbox.count() > 0:
            checkbox.check()

    page.get_by_role("link", name="次へ進む").click()


def fetch_availability(target_dates: list[date]) -> dict:
    """Launch headless Chromium, navigate, extract, and return the combined
    availability snapshot for `target_dates`.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            navigate_to_availability_page(page, target_dates)
            return extract_date_tables(page)
        finally:
            browser.close()
```

- [ ] **Step 2: Manual smoke test against the live site**

Run:
```bash
cd /Users/katsushifujiyoshi/github/tennis-booking
python -c "
from datetime import date
from src.dates import weekend_dates_in_range
from src.scraper import fetch_availability
import json

dates = weekend_dates_in_range(date.today(), 14)
result = fetch_availability(dates)
print(json.dumps(result, ensure_ascii=False, indent=2))
"
```
Expected: prints a JSON object keyed by ISO dates for the upcoming weekends, each containing
`A面`/`B面`/`C面`/`D面兼ゲートボール場` with 5 slot symbols each, with no exceptions raised.
If the site's selectors have drifted from what Task 5/6 assume, this command will raise or
print an empty/wrong structure — fix the selectors in `navigate_to_availability_page` before
proceeding.

- [ ] **Step 3: Commit**

```bash
cd /Users/katsushifujiyoshi/github/tennis-booking
git add src/scraper.py
git commit -m "feat: add live navigation from top page to 時間帯別空き状況"
```

---

### Task 7: Main orchestration entry point

**Files:**
- Create: `src/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `weekend_dates_in_range` (Task 1), `load_state`/`save_state` (Task 2), `find_new_openings` (Task 3), `build_message`/`send_discord_notification` (Task 4), `fetch_availability` (Task 6)
- Produces: `main() -> None` (script entry point, reads `DISCORD_WEBHOOK_URL` and `STATE_PATH` from environment)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_main.py`:
```python
import json
from datetime import date
from src import main as main_module


def test_main_sends_notification_when_new_opening(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}))

    monkeypatch.setenv("STATE_PATH", str(state_path))
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    monkeypatch.setattr(
        main_module, "weekend_dates_in_range",
        lambda start, num_days: [date(2026, 8, 22)],
    )
    monkeypatch.setattr(
        main_module, "fetch_availability",
        lambda dates: {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}},
    )

    sent = {}
    def fake_send(webhook_url, message):
        sent["webhook_url"] = webhook_url
        sent["message"] = message
    monkeypatch.setattr(main_module, "send_discord_notification", fake_send)

    main_module.main()

    assert sent["webhook_url"] == "https://discord.example/webhook"
    assert "A面" in sent["message"]
    assert json.loads(state_path.read_text()) == {
        "2026-08-22": {"A面": {"9:00〜11:00": "○"}}
    }


def test_main_does_not_notify_when_no_new_opening(tmp_path, monkeypatch):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}))

    monkeypatch.setenv("STATE_PATH", str(state_path))
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    monkeypatch.setattr(
        main_module, "weekend_dates_in_range",
        lambda start, num_days: [date(2026, 8, 22)],
    )
    monkeypatch.setattr(
        main_module, "fetch_availability",
        lambda dates: {"2026-08-22": {"A面": {"9:00〜11:00": "×"}}},
    )

    called = []
    monkeypatch.setattr(
        main_module, "send_discord_notification",
        lambda webhook_url, message: called.append(True),
    )

    main_module.main()

    assert called == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/katsushifujiyoshi/github/tennis-booking && python -m pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.main'`

- [ ] **Step 3: Implement**

Create `src/main.py`:
```python
import os
from datetime import date

from src.dates import weekend_dates_in_range
from src.state import load_state, save_state
from src.diff import find_new_openings
from src.notify import build_message, send_discord_notification
from src.scraper import fetch_availability


def main() -> None:
    state_path = os.environ.get("STATE_PATH", "state.json")
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]

    old_state = load_state(state_path)

    target_dates = weekend_dates_in_range(date.today(), 14)
    new_state = fetch_availability(target_dates)

    openings = find_new_openings(old_state, new_state)
    if openings:
        message = build_message(openings)
        send_discord_notification(webhook_url, message)

    save_state(state_path, new_state)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/katsushifujiyoshi/github/tennis-booking && python -m pytest tests/test_main.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Run the full test suite**

Run: `cd /Users/katsushifujiyoshi/github/tennis-booking && python -m pytest -v`
Expected: all tests pass (Tasks 1-7 combined)

- [ ] **Step 6: Commit**

```bash
cd /Users/katsushifujiyoshi/github/tennis-booking
git add src/main.py tests/test_main.py
git commit -m "feat: add main orchestration entry point"
```

---

### Task 8: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/watch.yml`

**Interfaces:**
- Consumes: `src/main.py` (Task 7) as the executed script; `DISCORD_WEBHOOK_URL` repository secret
- Produces: a scheduled CI job that updates `state.json` and pushes it only on change

- [ ] **Step 1: Implement**

Create `.github/workflows/watch.yml`:
```yaml
name: Watch Komaba tennis court availability

on:
  schedule:
    - cron: '*/5 * * * *'
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  watch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          python -m playwright install --with-deps chromium

      - name: Run watcher
        env:
          DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
        run: python -m src.main

      - name: Commit state.json if changed
        run: |
          if ! git diff --quiet -- state.json; then
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add state.json
            git commit -m "chore: update availability state"
            git push
          else
            echo "No state change, skipping commit."
          fi
```

- [ ] **Step 2: Verify the workflow file is valid YAML**

Run: `cd /Users/katsushifujiyoshi/github/tennis-booking && python -c "import yaml; yaml.safe_load(open('.github/workflows/watch.yml'))" `
Expected: no output, exit code 0 (if `pyyaml` is unavailable, instead visually confirm indentation matches the block above exactly)

- [ ] **Step 3: Commit**

```bash
cd /Users/katsushifujiyoshi/github/tennis-booking
git add .github/workflows/watch.yml
git commit -m "feat: add GitHub Actions workflow to run the watcher every 5 minutes"
```

- [ ] **Step 4: Push and register the Discord secret (manual, requires user)**

This step requires the user's Discord webhook URL and GitHub push access — hand off to them:
1. Push the branch: `git push -u origin main`
2. In the GitHub repo settings, add a repository secret named `DISCORD_WEBHOOK_URL` with the
   Discord webhook URL.
3. Manually trigger the workflow once (`gh workflow run watch.yml` or via the Actions tab)
   and confirm the run succeeds (`gh run list --workflow=watch.yml`).

---

### Task 9: README + final verification

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing (documentation only)
- Produces: nothing consumed by other tasks

- [ ] **Step 1: Update README**

Replace the contents of `README.md` with:
```markdown
# tennis-booking

目黒区施設予約システムの「駒場体育館 > 駒場庭球場」を5分おきに巡回し、
土日・直近2週間の枠に新しい空き（キャンセル等）が出たらDiscordに通知します。

## 仕組み

- `src/main.py` が Playwright でログイン不要の空き状況ページを巡回し、
  `state.json`（前回の空き状況）と比較して新規に空いた枠だけをDiscordに通知します。
- GitHub Actions (`.github/workflows/watch.yml`) が5分間隔でこれを実行します。
- v1では自動予約は行いません。ログイン情報は使用していません。

詳細設計: `docs/superpowers/specs/2026-08-16-meguro-tennis-watcher-design.md`

## セットアップ

1. Discordでこの通知を受け取りたいチャンネルのWebhook URLを作成する
   （チャンネル設定 → 連携サービス → Webhook）。
2. このリポジトリの Settings → Secrets and variables → Actions で
   `DISCORD_WEBHOOK_URL` という名前のシークレットに上記URLを登録する。
3. Actions タブから `Watch Komaba tennis court availability` を手動実行し、
   成功することを確認する。以降は5分おきに自動実行される。

## ローカル開発

```bash
pip install -r requirements.txt
python -m playwright install chromium
python -m pytest -v
```
```

- [ ] **Step 2: Run the full test suite one more time**

Run: `cd /Users/katsushifujiyoshi/github/tennis-booking && python -m pytest -v`
Expected: all tests pass

- [ ] **Step 3: Commit**

```bash
cd /Users/katsushifujiyoshi/github/tennis-booking
git add README.md
git commit -m "docs: describe the watcher and setup steps"
```
