#!/usr/bin/env python3
"""Copy remote harness to a Vast instance and start the matrix runner."""

from __future__ import annotations

from pathlib import Path

from lib.ssh_preflight import attach_instance_ssh
from lib.vast import ROOT, vastai_copy, vastai_execute

REMOTE_DIR = ROOT / "scripts" / "remote"
CONFIG_DIR = ROOT / "config"

MATRIX_START_CMD = (
    "chmod +x /workspace/bakeoff/onstart.sh /workspace/bakeoff/install_stack.sh && "
    "cd /workspace/bakeoff && "
    "nohup bash -lc './onstart.sh && python3 run_matrix.py; "
    "echo $? > /workspace/bakeoff/results/DONE' "
    ">/workspace/bakeoff/run.log 2>&1 &"
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
    print(f"Execute on {instance_id}{label}: {MATRIX_START_CMD[:80]}...")
    vastai_execute(instance_id, MATRIX_START_CMD)
    print(f"Started matrix on instance {instance_id}{label} — tail: vastai logs {instance_id}")
