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


def test_main_logs_fetch_summary(tmp_path, monkeypatch, capsys):
    fetched = {
        "2026-08-22": {
            "A面": {"9:00〜11:00": "○", "11:00〜13:00": "×"},
            "B面": {"9:00〜11:00": "×"},
        }
    }
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(fetched))

    monkeypatch.setenv("STATE_PATH", str(state_path))
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
    monkeypatch.setattr(
        main_module, "weekend_dates_in_range",
        lambda start, num_days: [date(2026, 8, 22)],
    )
    monkeypatch.setattr(
        main_module, "fetch_availability",
        lambda dates: fetched,
    )
    monkeypatch.setattr(main_module, "send_discord_notification", lambda *a: None)

    main_module.main()

    out = capsys.readouterr().out
    assert "3 slots" in out
    assert "1 open" in out
    assert "0 new opening" in out
    assert "state unchanged" in out


def test_main_logs_state_changed_when_no_new_opening(tmp_path, monkeypatch, capsys):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}))

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
    monkeypatch.setattr(main_module, "send_discord_notification", lambda *a: None)

    main_module.main()

    out = capsys.readouterr().out
    assert "state changed" in out
