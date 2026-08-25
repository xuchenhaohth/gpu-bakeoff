#!/usr/bin/env python3
"""Hugging Face dataset helpers for team-API result transfer."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DATASET = "gpu-bakeoff-results"


def resolve_hf_results_repo() -> str:
    """Return HF dataset repo id for bakeoff results."""
    repo = os.environ.get("HF_RESULTS_REPO", "").strip()
    if repo:
        return repo
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        raise RuntimeError("HF_TOKEN required to resolve HF_RESULTS_REPO")
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    who = api.whoami()
    username = who.get("name") or who.get("fullname") or "unknown"
    return f"{username}/{DEFAULT_DATASET}"


def pull_sku_from_hf(sku_id: str, dest_root: Path) -> None:
    """Download {sku_id}/** from the results dataset into dest_root/{sku_id}/."""
    from huggingface_hub import snapshot_download

    repo_id = resolve_hf_results_repo()
    token = os.environ.get("HF_TOKEN", "").strip() or None
    sku_dir = dest_root / sku_id
    sku_dir.mkdir(parents=True, exist_ok=True)
    print(f"Pull HF dataset {repo_id}:{sku_id}/ -> {sku_dir}")
    snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        allow_patterns=[f"{sku_id}/**"],
        local_dir=str(dest_root),
        token=token,
    )
