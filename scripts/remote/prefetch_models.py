#!/usr/bin/env python3
"""Prefetch Hugging Face weights listed in config/models.yaml."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REMOTE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = REMOTE_ROOT.parents[1]
sys.path.insert(0, str(REMOTE_ROOT))

import yaml  # noqa: E402


def config_path() -> Path:
    for base in (REMOTE_ROOT / "config", REPO_ROOT / "config"):
        p = base / "models.yaml"
        if p.exists():
            return p
    return REPO_ROOT / "config" / "models.yaml"


def main() -> int:
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ImportError:
        print("Install huggingface_hub")
        return 1

    token = os.environ.get("HF_TOKEN")
    models = yaml.safe_load(config_path().read_text()).get("models", {})
    cache_dir = os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))

    for key, spec in models.items():
        hf_id = spec.get("hf_id")
        if not hf_id:
            continue
        runtime = spec.get("runtime", "")
        layer = spec.get("layer_a", {})
        file_hint = layer.get("file_hint")

        if runtime == "llama_cpp" and file_hint:
            print(f"Prefetch GGUF {key}: {hf_id}/{file_hint}")
            try:
                path = hf_hub_download(
                    repo_id=str(hf_id),
                    filename=str(file_hint),
                    token=token,
                    cache_dir=cache_dir,
                )
                print(f"  -> {path}")
            except Exception as e:
                print(f"  WARN {key}: {e}")
            continue

        checkpoint = layer.get("checkpoint")
        if checkpoint and checkpoint != hf_id:
            print(f"Prefetch checkpoint {key}: {checkpoint}")
            try:
                snapshot_download(repo_id=str(checkpoint), token=token, cache_dir=cache_dir)
            except Exception as e:
                print(f"  WARN {key}: {e}")

        print(f"Prefetch {key}: {hf_id}")
        try:
            snapshot_download(repo_id=str(hf_id), token=token, cache_dir=cache_dir)
        except Exception as e:
            print(f"  WARN {key}: {e}")

    print(f"Cache dir: {cache_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
