#!/usr/bin/env python3
"""Poll a Vast instance until the matrix runner writes results/DONE."""

from __future__ import annotations

import os
import time

from lib.vast import vastai_execute_output
from lib.wait_running import FAIL_STATUSES, instance_status

MATRIX_TIMEOUT_SEC = int(os.environ.get("MATRIX_TIMEOUT_SEC", "28800"))
POLL = 30


def matrix_done(instance_id: int) -> bool:
    out = vastai_execute_output(
        instance_id,
        "test -f /workspace/bakeoff/results/DONE && echo yes",
    )
    return out.strip() == "yes"


def wait_for_matrix(instance_id: int) -> str:
    """Return 'done', a fail status, or 'timeout'."""
    deadline = time.time() + MATRIX_TIMEOUT_SEC
    while time.time() < deadline:
        status = instance_status(instance_id)
        if status in FAIL_STATUSES:
            print(f"  instance {instance_id} died during matrix: {status}")
            return status
        if matrix_done(instance_id):
            code = vastai_execute_output(
                instance_id,
                "cat /workspace/bakeoff/results/DONE 2>/dev/null || true",
            )
            print(f"  instance {instance_id} matrix finished (exit {code or '?'})")
            return "done"
        print(f"  instance {instance_id}: matrix running ({status})")
        time.sleep(POLL)
    print(f"  instance {instance_id}: matrix timeout after {MATRIX_TIMEOUT_SEC}s")
    return "timeout"
