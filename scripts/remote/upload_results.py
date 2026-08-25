#!/usr/bin/env python3
"""Upload bakeoff results to a Hugging Face dataset (team API / no SSH path)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from hf_auth import hf_token

REMOTE_ROOT = Path(__file__).resolve().parent
RESULTS_DIR = REMOTE_ROOT / "results"
ARTIFACTS_DIR = REMOTE_ROOT / "artifacts"
RUN_LOG = REMOTE_ROOT / "run.log"
MATRIX_CSV = RESULTS_DIR / "matrix.csv"
DEFAULT_DATASET = "gpu-bakeoff-results"

_repo_id: str | None = None


def _results_repo_id(token: str, *, create: bool) -> str:
    """Mirror lib/hf_results.py — remote harness has no scripts/lib/."""
    repo = os.environ.get("HF_RESULTS_REPO", "").strip()
    if repo:
        return repo
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    who = api.whoami()
    username = who.get("name") or who.get("fullname") or "unknown"
    repo_id = f"{username}/{DEFAULT_DATASET}"
    if create:
        api.create_repo(repo_id, repo_type="dataset", private=True, exist_ok=True)
    return repo_id


def ensure_repo(token: str | None = None) -> str | None:
    """Create dataset if needed; return repo id or None when HF_TOKEN unset."""
    global _repo_id
    if _repo_id:
        return _repo_id
    token = token or hf_token()
    if not token:
        return None
    _repo_id = _results_repo_id(token, create=True)
    return _repo_id


def path_in_repo(sku: str, path: Path) -> str:
    """Map local bakeoff path to dataset path ({sku}/matrix.csv, not {sku}/results/matrix.csv)."""
    rel = path.relative_to(REMOTE_ROOT).as_posix()
    if rel.startswith("results/"):
        rel = rel[len("results/") :]
    return f"{sku}/{rel}"


def upload_paths(repo_id: str, token: str, sku: str, paths: list[Path], *, label: str) -> None:
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    for path in paths:
        if not path.is_file():
            continue
        api.upload_file(
            path_or_fileobj=str(path),
            path_in_repo=path_in_repo(sku, path),
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=f"bakeoff {sku} {label} {path.name}",
        )


def upload_job(sku: str, artifact_path: str = "", transcript_path: str = "") -> bool:
    """Upload matrix.csv plus any new artifact files after one matrix job."""
    token = hf_token()
    if not token:
        return False
    repo_id = ensure_repo(token)
    if not repo_id:
        return False

    paths: list[Path] = []
    if MATRIX_CSV.is_file():
        paths.append(MATRIX_CSV)
    for rel in (artifact_path, transcript_path):
        if not rel:
            continue
        p = REMOTE_ROOT / rel
        if p.is_file():
            paths.append(p)
    if not paths:
        return False

    try:
        print(f"[progress] upload job {sku} ({len(paths)} file(s))")
        upload_paths(repo_id, token, sku, paths, label="job")
        return True
    except Exception as exc:
        print(f"WARN: upload_job failed: {exc}", file=sys.stderr)
        return False


def upload_all(sku: str) -> int:
    """Full SKU upload (end-of-run safety net)."""
    token = hf_token()
    if not token:
        print("HF_TOKEN unset — skipping results upload", file=sys.stderr)
        return 1

    repo_id = ensure_repo(token)
    if not repo_id:
        return 1

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


def main() -> int:
    sku = os.environ.get("BAKEOFF_SKU", "unknown")
    return upload_all(sku)


if __name__ == "__main__":
    raise SystemExit(main())
