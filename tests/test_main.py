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


def test_main_uses_s3_state_backend_when_configured(monkeypatch):
    import boto3
    from moto import mock_aws

    with mock_aws():
        monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket="test-bucket",
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )
        s3.put_object(
            Bucket="test-bucket",
            Key="state.json",
            Body=json.dumps({"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}).encode(),
        )

        monkeypatch.setenv("STATE_BACKEND", "s3")
        monkeypatch.setenv("STATE_BUCKET", "test-bucket")
        monkeypatch.setenv("STATE_KEY", "state.json")
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
        monkeypatch.setattr(
            main_module, "send_discord_notification",
            lambda url, msg: sent.update(url=url, msg=msg),
        )

        main_module.main()

        assert "A面" in sent["msg"]
        stored = json.loads(
            s3.get_object(Bucket="test-bucket", Key="state.json")["Body"].read()
        )
        assert stored == {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}}


def test_main_resolves_webhook_url_from_ssm_when_param_set(tmp_path, monkeypatch):
    import boto3
    from moto import mock_aws

    with mock_aws():
        monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
        ssm = boto3.client("ssm", region_name="ap-northeast-1")
        ssm.put_parameter(
            Name="/watcher/discord_webhook_url",
            Value="https://discord.example/from-ssm",
            Type="SecureString",
        )

        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"2026-08-22": {"A面": {"9:00〜11:00": "×"}}}))
        monkeypatch.setenv("STATE_PATH", str(state_path))
        monkeypatch.setenv("DISCORD_WEBHOOK_SSM_PARAM", "/watcher/discord_webhook_url")
        monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
        monkeypatch.setattr(
            main_module, "weekend_dates_in_range",
            lambda start, num_days: [date(2026, 8, 22)],
        )
        monkeypatch.setattr(
            main_module, "fetch_availability",
            lambda dates: {"2026-08-22": {"A面": {"9:00〜11:00": "○"}}},
        )
        sent = {}
        monkeypatch.setattr(
            main_module, "send_discord_notification",
            lambda url, msg: sent.update(url=url, msg=msg),
        )

        main_module.main()

        assert sent["url"] == "https://discord.example/from-ssm"


def test_lambda_handler_calls_main_and_returns_status_ok(monkeypatch):
    called = []
    monkeypatch.setattr(main_module, "main", lambda: called.append(True))

    result = main_module.lambda_handler({}, None)

    assert called == [True]
    assert result == {"statusCode": 200}


def test_main_uploads_failure_screenshot_to_s3_when_scrape_raises(tmp_path, monkeypatch):
    import boto3
    from moto import mock_aws

    with mock_aws():
        monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket="test-bucket",
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )

        monkeypatch.chdir(tmp_path)
        (tmp_path / "failure.png").write_bytes(b"fake-png-bytes")

        monkeypatch.setenv("STATE_BACKEND", "s3")
        monkeypatch.setenv("STATE_BUCKET", "test-bucket")
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
        monkeypatch.setattr(
            main_module, "weekend_dates_in_range",
            lambda start, num_days: [date(2026, 8, 22)],
        )

        def raise_scrape_error(dates):
            raise RuntimeError("scrape failed")

        monkeypatch.setattr(main_module, "fetch_availability", raise_scrape_error)

        try:
            main_module.main()
            raised = False
        except RuntimeError:
            raised = True

        assert raised
        uploaded = s3.get_object(Bucket="test-bucket", Key="failures/failure.png")["Body"].read()
        assert uploaded == b"fake-png-bytes"


def test_main_does_not_upload_when_no_failure_screenshot_exists(tmp_path, monkeypatch):
    import boto3
    from moto import mock_aws

    with mock_aws():
        monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
        s3 = boto3.client("s3", region_name="ap-northeast-1")
        s3.create_bucket(
            Bucket="test-bucket",
            CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        )

        monkeypatch.chdir(tmp_path)

        monkeypatch.setenv("STATE_BACKEND", "s3")
        monkeypatch.setenv("STATE_BUCKET", "test-bucket")
        monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example/webhook")
        monkeypatch.setattr(
            main_module, "weekend_dates_in_range",
            lambda start, num_days: [date(2026, 8, 22)],
        )
        monkeypatch.setattr(
            main_module, "fetch_availability",
            lambda dates: (_ for _ in ()).throw(RuntimeError("scrape failed")),
        )

        try:
            main_module.main()
        except RuntimeError:
            pass

        listed = s3.list_objects_v2(Bucket="test-bucket", Prefix="failures/")
        assert listed.get("KeyCount", 0) == 0
