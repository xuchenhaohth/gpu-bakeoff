#!/usr/bin/env python3
"""Upload bakeoff results to a Hugging Face dataset (team API / no SSH path)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REMOTE_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = REMOTE_ROOT / "results"
ARTIFACTS_DIR = REMOTE_ROOT / "artifacts"
RUN_LOG = REMOTE_ROOT / "run.log"
DEFAULT_DATASET = "gpu-bakeoff-results"


def resolve_repo(token: str) -> str:
    repo = os.environ.get("HF_RESULTS_REPO", "").strip()
    if repo:
        return repo
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    who = api.whoami()
    username = who.get("name") or who.get("fullname") or "unknown"
    repo_id = f"{username}/{DEFAULT_DATASET}"
    api.create_repo(repo_id, repo_type="dataset", private=True, exist_ok=True)
    return repo_id


def main() -> int:
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        print("HF_TOKEN unset — skipping results upload", file=sys.stderr)
        return 1

    sku = os.environ.get("BAKEOFF_SKU", "unknown")
    repo_id = resolve_repo(token)

    from huggingface_hub import HfApi

    api = HfApi(token=token)
    print(f"[progress] upload uploading to {repo_id}/{sku}")

    if RESULTS_DIR.is_dir():
        api.upload_folder(
            folder_path=str(RESULTS_DIR),
            path_in_repo=f"{sku}",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"bakeoff {sku} results",
        )
    if ARTIFACTS_DIR.is_dir():
        api.upload_folder(
            folder_path=str(ARTIFACTS_DIR),
            path_in_repo=f"{sku}/artifacts",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"bakeoff {sku} artifacts",
        )
    if RUN_LOG.is_file():
        api.upload_file(
            path_or_fileobj=str(RUN_LOG),
            path_in_repo=f"{sku}/run.log",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"bakeoff {sku} run.log",
        )

    print(f"[progress] upload complete {repo_id}/{sku}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
