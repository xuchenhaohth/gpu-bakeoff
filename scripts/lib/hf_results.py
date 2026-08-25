#!/usr/bin/env python3
"""Hugging Face dataset helpers for team-API result transfer."""

from __future__ import annotations

import os
from pathlib import Path

from lib.vast import hf_token

DEFAULT_DATASET = "gpu-bakeoff-results"


def _results_repo_id(create: bool = False) -> str:
    repo = os.environ.get("HF_RESULTS_REPO", "").strip()
    if repo:
        return repo
    token = hf_token()
    if not token:
        raise RuntimeError("HF_TOKEN required for Hugging Face results dataset")
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    who = api.whoami()
    username = who.get("name") or who.get("fullname") or "unknown"
    repo_id = f"{username}/{DEFAULT_DATASET}"
    if create:
        api.create_repo(repo_id, repo_type="dataset", private=True, exist_ok=True)
    return repo_id


def resolve_hf_results_repo() -> str:
    """Return HF dataset repo id (does not create the dataset)."""
    return _results_repo_id(create=False)


def ensure_hf_results_repo() -> str:
    """Return repo id, creating a private dataset when missing (write token required)."""
    return _results_repo_id(create=True)


def sku_matrix_path(dest_root: Path, sku_id: str) -> Path:
    return dest_root / sku_id / "matrix.csv"


def verify_sku_matrix(dest_root: Path, sku_id: str) -> None:
    path = sku_matrix_path(dest_root, sku_id)
    if not path.is_file():
        raise RuntimeError(f"Missing local results after pull: {path}")


def pull_sku_from_hf(sku_id: str, dest_root: Path) -> None:
    """Download {sku_id}/** from the results dataset into dest_root/{sku_id}/."""
    from huggingface_hub import HfApi, snapshot_download
    from huggingface_hub.utils import RepositoryNotFoundError

    repo_id = resolve_hf_results_repo()
    token = hf_token()
    sku_dir = dest_root / sku_id
    sku_dir.mkdir(parents=True, exist_ok=True)

    api = HfApi(token=token)
    try:
        api.repo_info(repo_id=repo_id, repo_type="dataset")
    except RepositoryNotFoundError as exc:
        raise RuntimeError(
            f"Hugging Face dataset not found: {repo_id}. "
            "Use a write-capable HF_TOKEN so upload_results can create it."
        ) from exc

    print(f"Pull HF dataset {repo_id}:{sku_id}/ -> {sku_dir}")
    try:
        snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            allow_patterns=[f"{sku_id}/**"],
            local_dir=str(dest_root),
            token=token,
        )
    except RepositoryNotFoundError as exc:
        raise RuntimeError(f"Hugging Face dataset not found during download: {repo_id}") from exc

    verify_sku_matrix(dest_root, sku_id)
