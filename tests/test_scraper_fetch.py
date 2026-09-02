import os
import socket
import tempfile
from datetime import date

from src import scraper
from src.scraper import fetch_availability, log_raw_tcp_connectivity


def test_fetch_availability_uses_unique_chromium_home_and_cleans_up(monkeypatch):
    # Site-hitting internals are stubbed; this test is only concerned with
    # the Chromium launch/cleanup behavior around them.
    monkeypatch.setattr(scraper, "navigate_to_availability_page", lambda page, dates: None)
    monkeypatch.setattr(
        scraper, "extract_date_tables", lambda page: {"2026-08-22": {}}
    )
    monkeypatch.setattr(scraper, "validate_extraction_result", lambda result, dates: None)

    created_dirs = []
    real_mkdtemp = tempfile.mkdtemp

    def spy_mkdtemp(*args, **kwargs):
        created = real_mkdtemp(*args, **kwargs)
        created_dirs.append(created)
        return created

    monkeypatch.setattr(tempfile, "mkdtemp", spy_mkdtemp)

    fetch_availability([date(2026, 8, 22)])
    fetch_availability([date(2026, 8, 22)])

    # Two separate launches must never be given the same HOME (and
    # therefore the same Chromium default profile dir) -- reusing one lets
    # a leftover SingletonLock from an aborted run break every later
    # launch that reuses the same warm Lambda execution environment.
    assert len(created_dirs) == 2
    assert created_dirs[0] != created_dirs[1]

    # Each directory must be removed once its launch is done, so nothing
    # persists into the next invocation on the same container.
    for created_dir in created_dirs:
        assert not os.path.exists(created_dir)


def test_log_raw_tcp_connectivity_reports_success(monkeypatch, capsys):
    # Distinguishes a Chromium-specific failure from a Lambda-network-level
    # one: on a real connection failure we want to know whether a plain
    # socket can reach the target host at all, independent of Chromium.
    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(socket, "create_connection", lambda addr, timeout: FakeSocket())

    log_raw_tcp_connectivity("example.com", 443)

    err = capsys.readouterr().err
    assert "example.com:443" in err
    assert "succeeded" in err


def test_log_raw_tcp_connectivity_reports_failure(monkeypatch, capsys):
    def raise_timeout(addr, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(socket, "create_connection", raise_timeout)

    log_raw_tcp_connectivity("example.com", 443)

    err = capsys.readouterr().err
    assert "example.com:443" in err
    assert "failed" in err
    assert "TimeoutError" in err
