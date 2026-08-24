"""Shared path helpers for the remote harness."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REMOTE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = REMOTE_ROOT.parents[1]
RESULTS_DIR = REMOTE_ROOT / "results"
ARTIFACTS_DIR = REMOTE_ROOT / "artifacts"
ASSETS_DIR = REMOTE_ROOT / "assets"
WORKFLOWS_DIR = ASSETS_DIR / "workflows"


def load_config(name: str) -> dict[str, Any]:
    for base in (REMOTE_ROOT / "config", REPO_ROOT / "config"):
        path = base / name
        if path.exists():
            return yaml.safe_load(path.read_text()) or {}
    return {}


def resolve_asset(path_str: str) -> Path:
    p = Path(path_str)
    if p.is_absolute():
        return p
    for base in (REMOTE_ROOT, ASSETS_DIR.parent):
        candidate = base / path_str
        if candidate.exists():
            return candidate
    return REMOTE_ROOT / path_str
