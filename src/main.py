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

    total_slots = sum(len(slots) for courts in new_state.values() for slots in courts.values())
    open_slots = sum(
        1
        for courts in new_state.values()
        for slots in courts.values()
        for symbol in slots.values()
        if symbol == "○"
    )
    print(
        f"[info] fetched {len(new_state)} dates, {total_slots} slots, "
        f"{open_slots} open"
    )

    openings = find_new_openings(old_state, new_state)
    print(f"[info] {len(openings)} new opening(s)")
    if openings:
        message = build_message(openings)
        send_discord_notification(webhook_url, message)

    print(f"[info] state {'changed' if new_state != old_state else 'unchanged'}")

    save_state(state_path, new_state)


if __name__ == "__main__":
    main()
