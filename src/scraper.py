import unicodedata
from datetime import date

from src.dates import parse_japanese_date

COURTS = ["A面", "B面", "C面", "D面兼ゲートボール場"]
SLOTS = ["9:00〜11:00", "11:00〜13:00", "13:00〜15:00", "15:00〜17:00", "17:00〜18:00"]

TOP_PAGE_URL = "https://resv.city.meguro.tokyo.jp/Web/"
FACILITY_NAME = "駒場体育館"
COURT_ROW_NAME = "駒場庭球場"


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
        # Each slot header's text is split across child <span> elements
        # (e.g. "9:00<span>～</span>11:00"), so a plain .strip() leaves
        # embedded whitespace/newlines between the pieces. Collapse all
        # whitespace with no separator to rejoin them, then convert the
        # live site's fullwidth tilde (U+FF5E "～") to the canonical wave
        # dash (U+301C "〜") that SLOTS uses -- these look alike but are
        # different code points, and NFKC does not map one to the other.
        raw_labels = [cell.inner_text() for cell in header_cells[2:]]
        slot_labels = ["".join(label.split()).replace("～", "〜") for label in raw_labels]

        rows = table.get_by_role("row").all()
        day_data = {}
        for row in rows[1:]:  # skip header row
            cells = row.get_by_role("cell").all()
            if not cells:
                continue
            # The live site renders court names with full-width Latin
            # letters (e.g. "Ａ面"); NFKC-normalize to the half-width form
            # COURTS uses (e.g. "A面") so both the live site and the
            # ASCII fixtures used in tests match the same way.
            court_name = unicodedata.normalize("NFKC", cells[0].inner_text().strip())
            if court_name not in COURTS:
                continue

            # Slot cells render their symbol as visible cell text in both
            # states the live site uses: read-only cells are plain
            # <td><label>×</label></td> with no <input>, and interactive
            # cells are <td><input type="checkbox">...<label>○</label></td>.
            # Neither carries the symbol in an aria-label attribute, so read
            # each slot cell's own text directly instead of going through
            # checkbox roles/attributes.
            slot_cells = cells[2:]
            slot_values = {}
            for slot_label, slot_cell in zip(slot_labels, slot_cells):
                slot_values[slot_label] = slot_cell.inner_text().strip()
            day_data[court_name] = slot_values

        result[iso_date] = day_data

    return result


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
    # dates are visible in one grid. Clicking 表示 triggers an in-place
    # AJAX refresh (no URL change) that briefly detaches the table. Waiting
    # for just the <table> element to attach is not enough: Chromium's
    # accessibility tree (which get_by_role queries against) can lag a
    # render frame or more behind the raw DOM after a large AJAX-driven
    # replacement, so column headers can still report zero results even
    # though row content already resolves. Wait for a specific, always-present
    # columnheader ("定員") instead -- that forces the wait to hold until the
    # accessibility tree itself has caught up with the new header row, not
    # just until some <table> exists in the DOM.
    page.get_by_role("radio", name="2週間").check()
    page.get_by_role("button", name="表示").click()
    page.get_by_role("columnheader", name="定員").first.wait_for()

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
            # Each checkbox is visually a toggle switch whose <label>
            # overlaps and intercepts pointer events, so a plain click is
            # rejected as not actionable. force=True still dispatches a
            # real click at the checkbox's coordinates, which the browser
            # forwards from the overlapping <label> to the input exactly
            # as a real user click would.
            checkbox.check(force=True)

    # This click is a full page navigation (施設別空き状況 -> 時間帯別空き状況),
    # unlike the 表示 click above. Wrap it so we wait for that navigation
    # to complete rather than racing extract_date_tables() against the
    # still-live previous page.
    with page.expect_navigation():
        page.get_by_role("link", name="次へ進む").click()


def validate_extraction_result(result: dict, target_dates: list[date]) -> None:
    """Raise if `result` (as returned by extract_date_tables) is missing an
    entry for any date in `target_dates`.

    An empty or incomplete result means navigation silently landed on an
    unexpected page (e.g. a session/ViewState hiccup or a site layout
    change the selectors missed) without raising. Per the spec's error
    handling contract, such site-structure drift must raise and exit 1,
    not be swallowed into an empty snapshot that would overwrite the
    committed state.json baseline and cause a silent monitoring blackout.
    """
    expected = {d.isoformat() for d in target_dates}
    actual = set(result.keys())
    if expected != actual:
        missing = expected - actual
        raise RuntimeError(
            "extract_date_tables returned an incomplete result "
            f"(missing dates: {sorted(missing)}); likely a site layout "
            "change or navigation failure -- refusing to overwrite state.json"
        )


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
            result = extract_date_tables(page)
            validate_extraction_result(result, target_dates)
            return result
        except Exception:
            import sys
            print(f"[error] fetch_availability failed at page.url = {page.url}", file=sys.stderr)
            raise
        finally:
            browser.close()
