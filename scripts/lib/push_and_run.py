#!/usr/bin/env python3
"""Copy remote harness to a Vast instance and start the matrix runner over SSH."""

from __future__ import annotations

import os

from lib.hf_env import REMOTE_HF_ENV_NAME, remote_hf_env_bytes
from lib.ssh_preflight import attach_instance_ssh
from lib.ssh_remote import (
    HARNESS_ROOT,
    HARNESS_START_SCRIPT,
    fetch_ssh_url,
    ssh_push_bytes,
    ssh_push_dir,
    ssh_run,
    verify_harness,
    wait_for_ssh,
)
from lib.vast import ROOT, read_yaml

REMOTE_DIR = ROOT / "scripts" / "remote"
CONFIG_DIR = ROOT / "config"
MATRIX_PATH = ROOT / "config" / "matrix.yaml"
REMOTE_HF_ENV = f"{HARNESS_ROOT}/{REMOTE_HF_ENV_NAME}"
REMOTE_SKU_ENV = f"{HARNESS_ROOT}/.env.sku"

_push_models: list[str] | None = None


def set_push_models(models: list[str] | None) -> None:
    global _push_models
    _push_models = models
    if models:
        os.environ["BAKEOFF_MODELS"] = ",".join(models)
    else:
        os.environ.pop("BAKEOFF_MODELS", None)


def sku_env_bytes(
    sku_id: str,
    gpu_count: int,
    models: list[str] | None = None,
    *,
    force: bool = False,
) -> bytes:
    lines = [f"BAKEOFF_SKU={sku_id}", f"BAKEOFF_GPU_COUNT={gpu_count}"]
    model_list = models or _push_models
    if model_list:
        lines.append(f"BAKEOFF_MODELS={','.join(model_list)}")
    skip_comfy = os.environ.get("BAKEOFF_SKIP_COMFY", "").strip()
    if skip_comfy:
        lines.append(f"BAKEOFF_SKIP_COMFY={skip_comfy}")
    llama_bin = os.environ.get("LLAMA_SERVER_BIN", "").strip()
    if llama_bin:
        lines.append(f"LLAMA_SERVER_BIN={llama_bin}")
    if force:
        lines.append("BAKEOFF_FORCE_RESTART=1")
    return ("\n".join(lines) + "\n").encode()


def gpu_count_for_sku(sku_id: str) -> int:
    matrix = read_yaml(MATRIX_PATH)
    meta = matrix.get("skus", {}).get(sku_id, {})
    return max(1, int(meta.get("num_gpus", 1)))


def push_sku_env(
    instance_id: int,
    sku_id: str,
    models: list[str] | None = None,
    *,
    force: bool = False,
) -> None:
    """SSH sessions do not inherit Docker -e; write SKU env for onstart/run_matrix."""
    count = gpu_count_for_sku(sku_id)
    ssh_push_bytes(
        instance_id,
        REMOTE_SKU_ENV,
        sku_env_bytes(sku_id, count, models, force=force),
    )


def push_hf_env(instance_id: int) -> None:
    """Write mode-600 .env.hf on the remote harness root (SSH sessions lack Docker -e)."""
    ssh_push_bytes(instance_id, REMOTE_HF_ENV, remote_hf_env_bytes())


def push_harness(instance_id: int, sku_id: str = "", *, force: bool = False) -> None:
    """Push harness + config into the container (same SSH path as smoke test)."""
    ssh_push_dir(instance_id, REMOTE_DIR, HARNESS_ROOT)
    ssh_push_dir(instance_id, CONFIG_DIR, f"{HARNESS_ROOT}/config")
    push_hf_env(instance_id)
    if sku_id:
        push_sku_env(instance_id, sku_id, force=force)
    verify_harness(instance_id)


def push_and_run(instance_id: int, sku_id: str = "", *, force: bool = False) -> None:
    label = f" ({sku_id})" if sku_id else ""
    attach_instance_ssh(instance_id)
    wait_for_ssh(instance_id)
    push_harness(instance_id, sku_id=sku_id, force=force)
    print(f"SSH start on {instance_id}{label}: bash {HARNESS_START_SCRIPT}")
    ssh_run(instance_id, f"bash {HARNESS_START_SCRIPT}", check=True, timeout=120)
    ssh_hint = fetch_ssh_url(instance_id)
    print(
        f"Started matrix on instance {instance_id}{label} — "
        f"progress polls PROGRESS.json over SSH; manual: "
        f"ssh to {ssh_hint} then tail -n 80 {HARNESS_ROOT}/run.log"
    )
