import os
import sys
import traceback

import boto3

from src.dates import weekend_and_holiday_dates_in_range, today_jst
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

    target_dates = weekend_and_holiday_dates_in_range(today_jst(), 14)
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


# Warm Lambda containers reused for many hours have repeatedly been
# observed to accumulate a Chromium/process-table resource leak (zombie
# processes, and possibly more) that eventually makes every subsequent
# browser launch fail. AWS's own recycling of a degraded environment has
# been observed taking 1-1.7 hours once that starts, so this proactively
# kills the process every N invocations to force a guaranteed-fresh
# environment well before the leak has been observed to become fatal.
_INVOCATION_LIMIT_BEFORE_RECYCLE = int(
    os.environ.get("INVOCATION_LIMIT_BEFORE_RECYCLE", "15")
)
_invocation_count = 0


def _read_kv_file(path: str, keys: tuple, divisor: int) -> dict:
    out = {}
    try:
        with open(path) as f:
            for line in f:
                parts = line.replace(":", " ").split()
                if len(parts) >= 2 and parts[0] in keys:
                    out[parts[0]] = int(parts[1]) // divisor
    except OSError:
        pass
    return out


def _log_memory_diagnostics() -> None:
    """Best-effort diagnostic: one line per invocation breaking down where
    memory goes, to tell whether the ~25MB/invocation growth in Lambda's
    "Max Memory Used" on a warm environment is a real leak (anon memory /
    leftover processes) or reclaimable page cache. It doesn't reproduce
    locally in the same image, so it has to be observed in Lambda itself.
    """
    try:
        meminfo = _read_kv_file(
            "/proc/meminfo",
            ("MemTotal", "MemAvailable", "AnonPages", "Cached", "Shmem", "Buffers"),
            1024,
        )
        cgroup = {}
        for path in ("/sys/fs/cgroup/memory.stat", "/sys/fs/cgroup/memory/memory.stat"):
            cgroup = _read_kv_file(path, ("anon", "file", "shmem", "rss", "cache"), 2**20)
            if cgroup:
                break
        self_status = _read_kv_file("/proc/self/status", ("VmRSS",), 1024)
        try:
            procs = []
            for pid in os.listdir("/proc"):
                if pid.isdigit():
                    try:
                        with open(f"/proc/{pid}/comm") as f:
                            procs.append(f.read().strip())
                    except OSError:
                        pass
        except OSError:
            procs = []
        tmp_bytes = 0
        tmp_entries = 0
        tmp_top = {}  # top-level /tmp entry -> total size in bytes
        for root, dirs, files in os.walk("/tmp"):
            tmp_entries += len(dirs) + len(files)
            top = os.path.relpath(root, "/tmp").split(os.sep)[0]
            for name in files:
                try:
                    size = os.lstat(os.path.join(root, name)).st_size
                except OSError:
                    continue
                tmp_bytes += size
                key = name if top == "." else top
                tmp_top[key] = tmp_top.get(key, 0) + size
        print(
            f"[diag] memory invocation={_invocation_count} meminfo_mb={meminfo} "
            f"cgroup_mb={cgroup} py_rss_mb={self_status.get('VmRSS')} "
            f"procs={len(procs)} {sorted(set(procs))} "
            f"tmp_entries={tmp_entries} tmp_mb={tmp_bytes // 2**20} "
            f"tmp_top_kb={ {k: v // 1024 for k, v in sorted(tmp_top.items())} }"
        )
    except Exception as e:  # never let a diagnostic break the invocation
        print(f"[diag] memory diagnostics failed: {type(e).__name__}: {e}")


def _should_recycle(count: int, limit: int) -> bool:
    return count >= limit


def lambda_handler(event, context):
    global _invocation_count
    _invocation_count += 1
    if not _should_recycle(_invocation_count, _INVOCATION_LIMIT_BEFORE_RECYCLE):
        try:
            main()
        finally:
            _log_memory_diagnostics()
        return {"statusCode": 200}

    # Run this invocation's check before exiting, so the recycle doesn't
    # cost a 5-minute slot. The exit still reports Runtime.ExitError; Lambda
    # async retries are disabled in Terraform so that error doesn't trigger
    # a duplicate run ~1 minute later.
    try:
        main()
    except Exception:
        # os._exit() below discards the in-flight exception, so print its
        # traceback explicitly or the failure would leave no trace in logs.
        traceback.print_exc()
    finally:
        _log_memory_diagnostics()
        print(
            f"[info] recycling execution environment after {_invocation_count} "
            "invocations to bound suspected warm-container resource leaks"
        )
        # os._exit() skips Python's normal interpreter shutdown, so buffered
        # output would otherwise be lost when stdout/stderr aren't a TTY
        # (the case under the Lambda runtime).
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)

if __name__ == "__main__":
    main()
