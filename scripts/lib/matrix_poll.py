#!/usr/bin/env python3
"""Poll a Vast instance until the matrix runner finishes."""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from lib.transport import use_onstart_transport
from lib.vast import vastai_logs
from lib.wait_running import FAIL_STATUSES, _format_duration, _truncate_msg, instance_status

MATRIX_TIMEOUT_SEC = int(os.environ.get("MATRIX_TIMEOUT_SEC", "28800"))
STARTUP_GRACE_SEC = int(os.environ.get("MATRIX_STARTUP_GRACE_SEC", "180"))
SSH_FAIL_LIMIT = int(os.environ.get("MATRIX_SSH_FAIL_LIMIT", "3"))
HEARTBEAT_STALE_SEC = int(os.environ.get("MATRIX_HEARTBEAT_STALE_SEC", "120"))
POLL = 30
KEEPALIVE_SEC = 300
UNCHANGED_WARN_SEC = 60
LOG_TAIL = 500
DONE_PATH = "/workspace/bakeoff/results/DONE"
PROGRESS_PATH = "/workspace/bakeoff/results/PROGRESS.json"
RUN_LOG_PATH = "/workspace/bakeoff/run.log"
HARNESS_PID_PATH = "/workspace/bakeoff/results/HARNESS.pid"

PROGRESS_MARKER = "[progress] "
DONE_MARKER = "BAKEOFF_DONE"
_BOOTSTRAP_MARKERS = ("== bakeoff bootstrap ==", "== bakeoff onstart ==")

_STATUS_CMD = (
    f"if test -f {DONE_PATH}; then "
    f"echo DONE:$(cat {DONE_PATH}); "
    f"elif test -f {PROGRESS_PATH}; then "
    f"cat {PROGRESS_PATH}; "
    f"else tail -n 30 {RUN_LOG_PATH} 2>/dev/null | sed '/^$/d' | tail -n 1; fi"
)

_HINT_SKIP_PREFIXES = (
    "Hit:",
    "Reading package",
    "Building dependency",
    "0 upgraded",
    "Server listening",
    "Warning: Permanently added",
)


@dataclass
class PollSnapshot:
    raw: str
    hint: str = ""
    heartbeat_age_sec: float | None = None


def remote_file_exists(instance_id: int, path: str) -> bool:
    from lib.ssh_remote import ssh_run

    out = ssh_run(instance_id, f"test -f {path} && echo yes", check=False, timeout=45)
    return out.strip() == "yes"


def matrix_done(instance_id: int) -> bool:
    if use_onstart_transport():
        return fetch_poll_snapshot(instance_id).raw.startswith("DONE:")
    return remote_file_exists(instance_id, DONE_PATH)


def harness_present(instance_id: int) -> bool:
    if use_onstart_transport():
        text = vastai_logs(instance_id, tail=300)
        if PROGRESS_MARKER in text:
            return True
        return any(marker in text for marker in _BOOTSTRAP_MARKERS)
    from lib.ssh_remote import ssh_run

    cmd = (
        f"if test -f {DONE_PATH}; then echo yes; "
        f"elif test -f {PROGRESS_PATH}; then echo yes; "
        f"elif test -f {HARNESS_PID_PATH} && kill -0 $(cat {HARNESS_PID_PATH}) 2>/dev/null; "
        f"then echo yes; else echo no; fi"
    )
    out = ssh_run(instance_id, cmd, check=False, timeout=45)
    return out.strip() == "yes"


def parse_log_hint(log_text: str) -> str:
    """Last meaningful non-progress line from container logs."""
    for line in reversed(log_text.splitlines()):
        text = line.strip()
        if not text or PROGRESS_MARKER in text:
            continue
        if text.startswith(_HINT_SKIP_PREFIXES):
            continue
        if (
            text.startswith("==")
            or text.startswith("WARN:")
            or text.startswith("Cloning")
            or "clone" in text.lower()
            or "pip install" in text.lower()
            or text.startswith("Downloading")
            or text.startswith("Installing")
            or text.startswith("Stack install")
        ):
            return _truncate_msg(text)
    return ""


def parse_logs_status(log_text: str) -> str:
    """Return DONE:code, a progress log line, or empty."""
    return parse_logs_detail(log_text)[0]


def _try_live_pull(
    instance_id: int,
    sku_id: str,
    raw: str,
    last_pulled_job: int,
) -> int:
    """Pull results locally when a job completes; return updated last_pulled_job."""
    from lib.pull_results import live_pull_sku

    should_pull, new_last = _should_live_pull(raw, last_pulled_job)
    if raw.startswith("DONE:"):
        should_pull = True
    if not should_pull:
        return last_pulled_job
    try:
        live_pull_sku(instance_id, sku_id)
        updated = max(last_pulled_job, new_last)
        label = "done" if raw.startswith("DONE:") else f"job {updated}"
        print(f"  instance {instance_id}: live pull {sku_id} ({label})")
        return updated
    except Exception as exc:
        print(f"  instance {instance_id}: live pull failed: {exc}")
        return last_pulled_job


def parse_logs_detail(log_text: str) -> tuple[str, str]:
    """Return (status_raw, hint) from container logs."""
    last_progress = ""
    done_code: str | None = None
    for line in log_text.splitlines():
        if DONE_MARKER in line:
            match = re.search(r"exit=(\d+)", line)
            done_code = match.group(1) if match else "?"
        if PROGRESS_MARKER in line:
            last_progress = line.split(PROGRESS_MARKER, 1)[1].strip()
    if done_code is not None:
        return f"DONE:{done_code}", ""
    if last_progress:
        return f"log={last_progress}", parse_log_hint(log_text)
    return "", parse_log_hint(log_text)


def progress_json_age_sec(data: dict[str, Any]) -> float | None:
    updated = data.get("updated_at")
    if not updated:
        return None
    try:
        ts = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds())
    except ValueError:
        return None


def fetch_poll_snapshot(instance_id: int, *, tail: int = LOG_TAIL) -> PollSnapshot:
    if use_onstart_transport():
        log_text = vastai_logs(instance_id, tail=tail)
        raw, hint = parse_logs_detail(log_text)
        return PollSnapshot(raw=raw, hint=hint)

    from lib.ssh_remote import ssh_run

    raw = ssh_run(instance_id, _STATUS_CMD, check=True, timeout=45)
    age: float | None = None
    if raw.strip().startswith("{"):
        try:
            data: dict[str, Any] = json.loads(raw)
            age = progress_json_age_sec(data)
        except json.JSONDecodeError:
            pass
    return PollSnapshot(raw=raw, heartbeat_age_sec=age)


def status_is_blank(raw: str) -> bool:
    """True when the remote has no DONE, PROGRESS.json, or run.log line yet."""
    text = raw.strip()
    if not text:
        return True
    if text.startswith("{"):
        try:
            data: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError:
            return False
        return not data.get("phase") and not data.get("message")
    if text.startswith("log="):
        return not text[4:].strip()
    return False


def _unchanged_bucket(seconds: float) -> int:
    if seconds < UNCHANGED_WARN_SEC:
        return 0
    return int(seconds // 60)


def _append_json_fields(parts: list[str], data: dict[str, Any]) -> None:
    phase = str(data.get("phase", "?"))
    parts.append(phase)
    if phase == "prefetch":
        pi = data.get("prefetch_index")
        pt = data.get("prefetch_total")
        if pi is not None and pt is not None:
            parts.append(f"{pi}/{pt}")
        model = data.get("model")
        if model:
            parts.append(str(model))
    elif phase == "matrix":
        ji = data.get("job_index")
        jt = data.get("job_total")
        if ji is not None and jt is not None:
            parts.append(f"{ji}/{jt}")
        model = data.get("model")
        prompt_id = data.get("prompt_id")
        if model and prompt_id:
            parts.append(f"{model}/{prompt_id}")
        elif model:
            parts.append(str(model))
        stage = data.get("stage")
        if stage:
            parts.append(str(stage))
        last = data.get("last_result")
        if last:
            parts.append(f"last={last}")
    else:
        msg = data.get("message")
        if msg:
            parts.append(str(msg))
        model = data.get("model")
        if model:
            parts.append(str(model))


def format_progress_line(
    instance_id: int,
    raw: str,
    elapsed: float,
    remaining: float,
    *,
    unchanged_sec: float | None = None,
    heartbeat_age: float | None = None,
) -> str:
    parts: list[str] = [f"instance {instance_id}:"]

    if raw.startswith("DONE:"):
        parts.append("finished")
    elif raw.strip().startswith("{"):
        try:
            data: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError:
            data = {}
        if data:
            _append_json_fields(parts, data)
            hb = heartbeat_age if heartbeat_age is not None else progress_json_age_sec(data)
            if hb is not None and hb >= HEARTBEAT_STALE_SEC:
                parts.append(f"heartbeat_stale={_format_duration(hb)}")
        else:
            parts.append("waiting")
    elif raw.strip():
        if raw.startswith("log="):
            parts.append(raw[4:].strip())
        else:
            parts.append(f"log={_truncate_msg(raw.strip())}")
    else:
        parts.append("waiting")

    parts.append(f"{_format_duration(elapsed)} elapsed")
    if remaining > 0:
        parts.append(f"{_format_duration(remaining)} left")
    if unchanged_sec is not None and unchanged_sec >= UNCHANGED_WARN_SEC:
        parts.append(f"(unchanged {_format_duration(unchanged_sec)})")

    return "  " + "  ".join(parts)


def format_hint_line(instance_id: int, hint: str) -> str:
    return f"    hint: {_truncate_msg(hint)} (see: vastai logs {instance_id} --tail 80)"


def _should_print_progress(
    *,
    print_key: str,
    last_print_key: str,
    last_print_time: float,
    now: float,
) -> bool:
    if print_key != last_print_key:
        return True
    return (now - last_print_time) >= KEEPALIVE_SEC


def _job_index_from_raw(raw: str) -> int | None:
    text = raw.strip()
    if text.startswith("{"):
        try:
            data: dict[str, Any] = json.loads(text)
        except json.JSONDecodeError:
            return None
        ji = data.get("job_index")
        return int(ji) if ji is not None else None
    if text.startswith("log="):
        text = text[4:].strip()
    match = re.search(r"matrix\s+(\d+)/\d+", text)
    if match:
        return int(match.group(1))
    return None


def _should_live_pull(raw: str, last_pulled_job: int) -> tuple[bool, int]:
    """True when a completed job or upload warrants a local pull."""
    ji = _job_index_from_raw(raw)
    if ji is None or ji <= last_pulled_job:
        if "upload" in raw.lower() and last_pulled_job > 0:
            return True, last_pulled_job
        return False, last_pulled_job
    lowered = raw.lower()
    if "done" in lowered or "upload" in lowered or "last=" in lowered:
        return True, ji
    return False, last_pulled_job


def wait_for_matrix(instance_id: int, sku_id: str = "") -> str:
    """Return 'done', a fail status, or 'timeout'."""
    start = time.time()
    deadline = start + MATRIX_TIMEOUT_SEC
    ssh_fails = 0
    status_first_seen = time.time()
    last_status_key = ""
    last_print_key = ""
    last_print_time = 0.0
    last_pulled_job = 0

    while time.time() < deadline:
        now = time.time()
        status = instance_status(instance_id)
        if status is not None and status in FAIL_STATUSES:
            print(f"  instance {instance_id} died during matrix: {status}")
            return status

        try:
            snap = fetch_poll_snapshot(instance_id)
            raw = snap.raw
            ssh_fails = 0
        except (RuntimeError, OSError, TimeoutError) as exc:
            ssh_fails += 1
            print(
                f"  instance {instance_id}: ssh error "
                f"({ssh_fails}/{SSH_FAIL_LIMIT}): {exc}"
            )
            if ssh_fails >= SSH_FAIL_LIMIT:
                print(
                    f"  instance {instance_id}: aborting — SSH failed {SSH_FAIL_LIMIT} times"
                )
                return "ssh_failed"
            time.sleep(POLL)
            continue

        if raw.startswith("DONE:"):
            code = raw.split(":", 1)[1].strip()
            if sku_id:
                last_pulled_job = _try_live_pull(instance_id, sku_id, raw, last_pulled_job)
            print(f"  instance {instance_id} matrix finished (exit {code or '?'})")
            return "done"

        if sku_id:
            last_pulled_job = _try_live_pull(instance_id, sku_id, raw, last_pulled_job)

        status_key = raw.strip()
        if status_key != last_status_key:
            status_first_seen = now
            last_status_key = status_key

        unchanged_sec = now - status_first_seen
        unchanged_bucket = _unchanged_bucket(unchanged_sec)
        show_hint = use_onstart_transport() and unchanged_sec >= UNCHANGED_WARN_SEC
        hint = snap.hint if show_hint else ""
        print_key = f"{status_key}|{hint}|{unchanged_bucket}"

        if _should_print_progress(
            print_key=print_key,
            last_print_key=last_print_key,
            last_print_time=last_print_time,
            now=now,
        ):
            print(
                format_progress_line(
                    instance_id,
                    raw,
                    now - start,
                    deadline - now,
                    unchanged_sec=unchanged_sec if unchanged_bucket else None,
                    heartbeat_age=snap.heartbeat_age_sec,
                )
            )
            if hint:
                print(format_hint_line(instance_id, hint))
            last_print_key = print_key
            last_print_time = now

        if status_is_blank(raw) and (now - start) >= STARTUP_GRACE_SEC:
            print(
                f"  instance {instance_id}: no progress in logs/files after "
                f"{STARTUP_GRACE_SEC}s — harness did not start"
            )
            return "no_progress"
        time.sleep(POLL)

    print(f"  instance {instance_id}: matrix timeout after {MATRIX_TIMEOUT_SEC}s")
    return "timeout"
