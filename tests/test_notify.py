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
