#!/usr/bin/env python3
"""Copy remote harness to a Vast instance and start the matrix runner over SSH."""

from __future__ import annotations

from pathlib import Path

from lib.ssh_preflight import attach_instance_ssh
from lib.ssh_remote import fetch_ssh_url, ssh_run
from lib.vast import ROOT, vastai_copy

REMOTE_DIR = ROOT / "scripts" / "remote"
CONFIG_DIR = ROOT / "config"

MATRIX_START_CMD = (
    "chmod +x /workspace/bakeoff/onstart.sh /workspace/bakeoff/install_stack.sh && "
    "mkdir -p /workspace/bakeoff/results && "
    "cd /workspace/bakeoff && "
    "setsid nohup bash -lc './onstart.sh && python3 run_matrix.py; "
    "echo $? > /workspace/bakeoff/results/DONE' "
    ">/workspace/bakeoff/run.log 2>&1 < /dev/null &"
)


def copy_to(instance_id: int, local: Path, remote: str) -> None:
    src = f"local:{local}/"
    dst = f"{instance_id}:{remote}"
    print(f"Copy {src} -> {dst}")
    vastai_copy(src, dst)


def push_and_run(instance_id: int, sku_id: str = "") -> None:
    label = f" ({sku_id})" if sku_id else ""
    attach_instance_ssh(instance_id)
    copy_to(instance_id, REMOTE_DIR, "/workspace/bakeoff/")
    copy_to(instance_id, CONFIG_DIR, "/workspace/bakeoff/config/")
    print(f"SSH start on {instance_id}{label}: {MATRIX_START_CMD[:80]}...")
    ssh_run(instance_id, MATRIX_START_CMD, check=True, timeout=90)
    ssh_hint = fetch_ssh_url(instance_id)
    print(
        f"Started matrix on instance {instance_id}{label} — "
        f"progress polls PROGRESS.json over SSH; manual: "
        f"ssh to {ssh_hint} then tail -n 80 /workspace/bakeoff/run.log"
    )
