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
