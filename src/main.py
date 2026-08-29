import os
from datetime import date

import boto3

from src.dates import weekend_dates_in_range
from src.state import load_state, save_state, load_state_s3, save_state_s3
from src.diff import find_new_openings
from src.notify import build_message, send_discord_notification
from src.scraper import fetch_availability


def _load_state() -> dict:
    if os.environ.get("STATE_BACKEND") == "s3":
        return load_state_s3(os.environ["STATE_BUCKET"], os.environ.get("STATE_KEY", "state.json"))
    return load_state(os.environ.get("STATE_PATH", "state.json"))


def _save_state(data: dict) -> None:
    if os.environ.get("STATE_BACKEND") == "s3":
        save_state_s3(os.environ["STATE_BUCKET"], os.environ.get("STATE_KEY", "state.json"), data)
    else:
        save_state(os.environ.get("STATE_PATH", "state.json"), data)


def _get_webhook_url() -> str:
    param_name = os.environ.get("DISCORD_WEBHOOK_SSM_PARAM")
    if param_name:
        ssm = boto3.client("ssm")
        return ssm.get_parameter(Name=param_name, WithDecryption=True)["Parameter"]["Value"]
    return os.environ["DISCORD_WEBHOOK_URL"]


def _upload_failure_screenshot() -> None:
    """Best-effort upload of scraper.py's failure.png (written to cwd) to S3.

    scraper.py writes a relative "failure.png" on scrape failure and is not
    modified by this migration. In the Lambda container the working
    directory is /tmp (writable), so this just needs to pick that file up
    and ship it somewhere retrievable after the invocation ends.
    """
    bucket = os.environ.get("STATE_BUCKET")
    if not bucket or not os.path.exists("failure.png"):
        return
    s3 = boto3.client("s3")
    s3.upload_file("failure.png", bucket, "failures/failure.png")
    print("[info] uploaded failure.png to s3://" + bucket + "/failures/failure.png")


def main() -> None:
    webhook_url = _get_webhook_url()
    old_state = _load_state()

    target_dates = weekend_dates_in_range(date.today(), 14)
    try:
        new_state = fetch_availability(target_dates)
    except Exception:
        _upload_failure_screenshot()
        raise

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

    _save_state(new_state)


def lambda_handler(event, context):
    main()
    return {"statusCode": 200}


if __name__ == "__main__":
    main()
