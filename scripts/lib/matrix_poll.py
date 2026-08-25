#!/usr/bin/env python3
"""Poll a Vast instance until the matrix runner writes results/DONE."""

from __future__ import annotations

import json
import os
import time
from typing import Any

from lib.ssh_remote import ssh_run
from lib.wait_running import FAIL_STATUSES, _format_duration, _truncate_msg, instance_status

MATRIX_TIMEOUT_SEC = int(os.environ.get("MATRIX_TIMEOUT_SEC", "28800"))
STARTUP_GRACE_SEC = int(os.environ.get("MATRIX_STARTUP_GRACE_SEC", "180"))
SSH_FAIL_LIMIT = int(os.environ.get("MATRIX_SSH_FAIL_LIMIT", "3"))
POLL = 30
DONE_PATH = "/workspace/bakeoff/results/DONE"
PROGRESS_PATH = "/workspace/bakeoff/results/PROGRESS.json"
RUN_LOG_PATH = "/workspace/bakeoff/run.log"
HARNESS_PATH = "/workspace/bakeoff/onstart.sh"

_STATUS_CMD = (
    f"if test -f {DONE_PATH}; then "
    f"echo DONE:$(cat {DONE_PATH}); "
    f"elif test -f {PROGRESS_PATH}; then "
    f"cat {PROGRESS_PATH}; "
    f"else tail -n 30 {RUN_LOG_PATH} 2>/dev/null | sed '/^$/d' | tail -n 1; fi"
)


def remote_file_exists(instance_id: int, path: str) -> bool:
    out = ssh_run(instance_id, f"test -f {path} && echo yes", check=False, timeout=45)
    return out.strip() == "yes"


def matrix_done(instance_id: int) -> bool:
    return remote_file_exists(instance_id, DONE_PATH)


def harness_present(instance_id: int) -> bool:
    return remote_file_exists(instance_id, HARNESS_PATH)


def fetch_matrix_status(instance_id: int) -> str:
    return ssh_run(instance_id, _STATUS_CMD, check=True, timeout=45)


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
    return False


def format_progress_line(
    instance_id: int,
    raw: str,
    elapsed: float,
    remaining: float,
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
            else:
                msg = data.get("message")
                if msg:
                    parts.append(str(msg))
                model = data.get("model")
                if model:
                    parts.append(str(model))
            last = data.get("last_result")
            if last:
                parts.append(f"last={last}")
        else:
            parts.append("waiting")
    elif raw.strip():
        parts.append(f"log={_truncate_msg(raw.strip())}")
    else:
        parts.append("waiting")

    parts.append(f"{_format_duration(elapsed)} elapsed")
    if remaining > 0:
        parts.append(f"{_format_duration(remaining)} left")

    return "  " + "  ".join(parts)


def wait_for_matrix(instance_id: int) -> str:
    """Return 'done', a fail status, or 'timeout'."""
    start = time.time()
    deadline = start + MATRIX_TIMEOUT_SEC
    ssh_fails = 0
    while time.time() < deadline:
        now = time.time()
        status = instance_status(instance_id)
        if status is not None and status in FAIL_STATUSES:
            print(f"  instance {instance_id} died during matrix: {status}")
            return status

        try:
            raw = fetch_matrix_status(instance_id)
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
            print(f"  instance {instance_id} matrix finished (exit {code or '?'})")
            return "done"

        elapsed = now - start
        remaining = deadline - now
        print(format_progress_line(instance_id, raw, elapsed, remaining))
        if status_is_blank(raw) and elapsed >= STARTUP_GRACE_SEC:
            print(
                f"  instance {instance_id}: no PROGRESS.json or run.log after "
                f"{STARTUP_GRACE_SEC}s — harness did not start"
            )
            return "no_progress"
        time.sleep(POLL)

    print(f"  instance {instance_id}: matrix timeout after {MATRIX_TIMEOUT_SEC}s")
    return "timeout"
