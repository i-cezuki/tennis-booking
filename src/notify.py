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
