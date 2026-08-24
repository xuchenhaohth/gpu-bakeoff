#!/usr/bin/env python3
"""Poll a Vast instance until the matrix runner writes results/DONE."""

from __future__ import annotations

import os
import time

from lib.vast import vastai_execute_output
from lib.wait_running import FAIL_STATUSES, instance_status, status_display

MATRIX_TIMEOUT_SEC = int(os.environ.get("MATRIX_TIMEOUT_SEC", "28800"))
POLL = 30
DONE_PATH = "/workspace/bakeoff/results/DONE"
HARNESS_PATH = "/workspace/bakeoff/onstart.sh"


def remote_file_exists(instance_id: int, path: str) -> bool:
    out = vastai_execute_output(instance_id, f"test -f {path} && echo yes")
    return out.strip() == "yes"


def matrix_done(instance_id: int) -> bool:
    return remote_file_exists(instance_id, DONE_PATH)


def harness_present(instance_id: int) -> bool:
    return remote_file_exists(instance_id, HARNESS_PATH)


def wait_for_matrix(instance_id: int) -> str:
    """Return 'done', a fail status, or 'timeout'."""
    deadline = time.time() + MATRIX_TIMEOUT_SEC
    while time.time() < deadline:
        status = instance_status(instance_id)
        if status is not None and status in FAIL_STATUSES:
            print(f"  instance {instance_id} died during matrix: {status}")
            return status
        if matrix_done(instance_id):
            code = vastai_execute_output(
                instance_id,
                f"cat {DONE_PATH} 2>/dev/null || true",
            )
            print(f"  instance {instance_id} matrix finished (exit {code or '?'})")
            return "done"
        print(f"  instance {instance_id}: matrix running ({status_display(status)})")
        time.sleep(POLL)
    print(f"  instance {instance_id}: matrix timeout after {MATRIX_TIMEOUT_SEC}s")
    return "timeout"
