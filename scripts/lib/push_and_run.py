#!/usr/bin/env python3
"""Copy remote harness to a Vast instance and start the matrix runner over SSH."""

from __future__ import annotations

from pathlib import Path

from lib.ssh_preflight import attach_instance_ssh
from lib.ssh_remote import (
    fetch_ssh_url,
    HARNESS_ROOT,
    HARNESS_START_SCRIPT,
    ssh_push_dir,
    ssh_run,
    verify_harness,
    wait_for_ssh,
)
from lib.vast import ROOT

REMOTE_DIR = ROOT / "scripts" / "remote"
CONFIG_DIR = ROOT / "config"


def push_harness(instance_id: int) -> None:
    """Push harness + config into the container (same SSH path as smoke test)."""
    ssh_push_dir(instance_id, REMOTE_DIR, HARNESS_ROOT)
    ssh_push_dir(instance_id, CONFIG_DIR, f"{HARNESS_ROOT}/config")
    verify_harness(instance_id)


def push_and_run(instance_id: int, sku_id: str = "") -> None:
    label = f" ({sku_id})" if sku_id else ""
    attach_instance_ssh(instance_id)
    wait_for_ssh(instance_id)
    push_harness(instance_id)
    print(f"SSH start on {instance_id}{label}: bash {HARNESS_START_SCRIPT}")
    ssh_run(instance_id, f"bash {HARNESS_START_SCRIPT}", check=True, timeout=120)
    ssh_hint = fetch_ssh_url(instance_id)
    print(
        f"Started matrix on instance {instance_id}{label} — "
        f"progress polls PROGRESS.json over SSH; manual: "
        f"ssh to {ssh_hint} then tail -n 80 {HARNESS_ROOT}/run.log"
    )
