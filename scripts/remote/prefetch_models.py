#!/usr/bin/env python3
"""Prefetch Hugging Face weights listed in config/models.yaml."""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

REMOTE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = REMOTE_ROOT.parents[1]
sys.path.insert(0, str(REMOTE_ROOT))

import yaml  # noqa: E402
from hf_auth import hf_token  # noqa: E402
from model_spec import model_selected, resolve_model_spec  # noqa: E402
from progress import write_progress  # noqa: E402


def config_path() -> Path:
    for base in (REMOTE_ROOT / "config", REPO_ROOT / "config"):
        p = base / "models.yaml"
        if p.exists():
            return p
    return REPO_ROOT / "config" / "models.yaml"


def prefetch_targets(models: dict, sku: str) -> list[tuple[str, dict]]:
    """Models that will be downloaded (one entry per progress tick)."""
    targets: list[tuple[str, dict]] = []
    for key, spec in models.items():
        if not model_selected(key):
            continue
        resolved = resolve_model_spec(spec, sku)
        if not resolved.get("hf_id"):
            continue
        targets.append((key, resolved))
    return targets


def _heartbeat(message: str, stop: threading.Event, interval: float = 30.0) -> None:
    while not stop.wait(interval):
        write_progress("prefetch", message=message)


def download_with_heartbeat(fn, message: str) -> None:
    stop = threading.Event()
    thread = threading.Thread(target=_heartbeat, args=(message, stop), daemon=True)
    thread.start()
    try:
        fn()
    finally:
        stop.set()
        thread.join(timeout=2)


def main() -> int:
    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ImportError:
        print("Install huggingface_hub")
        return 1

    token = hf_token()
    sku = os.environ.get("BAKEOFF_SKU", "unknown")
    models = yaml.safe_load(config_path().read_text()).get("models", {})
    cache_dir = os.environ.get("HF_HOME", str(Path.home() / ".cache" / "huggingface"))
    targets = prefetch_targets(models, sku)
    total = len(targets)
    errors: list[str] = []

    for index, (key, spec) in enumerate(targets, start=1):
        hf_id = spec.get("hf_id")
        if not hf_id:
            continue
        runtime = spec.get("runtime", "")
        layer = spec.get("layer_a", {})
        file_hint = layer.get("file_hint")

        write_progress(
            "prefetch",
            model=key,
            prefetch_index=index,
            prefetch_total=total,
            message=f"Prefetch {key}",
        )

        if runtime == "llama_cpp" and file_hint:
            print(f"Prefetch GGUF {key}: {hf_id}/{file_hint}")
            try:
                path_holder: dict[str, str] = {}

                def _gguf_download() -> None:
                    path_holder["path"] = hf_hub_download(
                        repo_id=str(hf_id),
                        filename=str(file_hint),
                        token=token,
                        cache_dir=cache_dir,
                    )

                download_with_heartbeat(
                    _gguf_download,
                    f"prefetch: downloading {file_hint}",
                )
                path = path_holder.get("path", "")
                if not path or not Path(path).is_file():
                    msg = f"{key}: GGUF missing after download {hf_id}/{file_hint}"
                    print(f"  ERROR {msg}")
                    errors.append(msg)
                else:
                    print(f"  -> {path}")
            except Exception as e:
                msg = f"{key}: {e}"
                print(f"  ERROR {msg}")
                errors.append(msg)
            continue

        checkpoint = layer.get("checkpoint")
        if checkpoint and checkpoint != hf_id:
            print(f"Prefetch checkpoint {key}: {checkpoint}")
            try:
                download_with_heartbeat(
                    lambda: snapshot_download(repo_id=str(checkpoint), token=token, cache_dir=cache_dir),
                    f"prefetch: snapshot {checkpoint}",
                )
            except Exception as e:
                print(f"  WARN {key}: {e}")

        if runtime == "vllm" and checkpoint:
            print(f"Prefetch {key}: using checkpoint {checkpoint}")
            continue

        print(f"Prefetch {key}: {hf_id}")
        try:
            download_with_heartbeat(
                lambda: snapshot_download(repo_id=str(hf_id), token=token, cache_dir=cache_dir),
                f"prefetch: snapshot {hf_id}",
            )
        except Exception as e:
            print(f"  WARN {key}: {e}")

    print(f"Cache dir: {cache_dir}")
    if errors:
        print("Prefetch failed:")
        for err in errors:
            print(f"  - {err}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
