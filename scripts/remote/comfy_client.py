#!/usr/bin/env python3
"""ComfyUI diffusion job client."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import comfy_api
from workflow_loader import inject_params, load_workflow

COMFY_PORT = int(os.environ.get("COMFY_PORT", "8188"))
COMFY_STARTUP_SEC = int(os.environ.get("COMFY_STARTUP_SEC", "45"))
COMFY_DIR = Path("/workspace/ComfyUI")
COMFY_LOG = Path("/workspace/bakeoff/comfy.log")


def _comfy_log_tail(n: int = 20) -> str:
    if not COMFY_LOG.is_file():
        return "(no comfy.log)"
    try:
        lines = COMFY_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:]) if lines else "(empty comfy.log)"
    except OSError as exc:
        return f"(could not read comfy.log: {exc})"


def _comfy_start_error(model: str, seed: int) -> dict:
    return {
        "mode": "comfyui",
        "status": "error",
        "pass": False,
        "model": model,
        "seed": seed,
        "error": "ComfyUI did not start",
        "note": _comfy_log_tail(),
    }


def start_comfy(background: bool = True) -> None:
    if comfy_api.server_up():
        return
    comfy = COMFY_DIR / "main.py"
    if not comfy.exists():
        return
    if background:
        COMFY_LOG.parent.mkdir(parents=True, exist_ok=True)
        log_fh = COMFY_LOG.open("a", encoding="utf-8")
        subprocess.Popen(
            ["python3", str(comfy), "--listen", "0.0.0.0", "--port", str(COMFY_PORT)],
            stdout=log_fh,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + COMFY_STARTUP_SEC
        last_progress = 0.0
        while time.monotonic() < deadline:
            if comfy_api.server_up():
                return
            now = time.monotonic()
            if now - last_progress >= 15:
                try:
                    from progress import write_progress  # noqa: PLC0415

                    write_progress(
                        "comfy_wait",
                        message=f"waiting for ComfyUI :{COMFY_PORT}",
                    )
                except Exception:
                    pass
                last_progress = now
            time.sleep(2)


def _run_comfy_workflow(
    model_key: str,
    prompt: str,
    seed: int,
    resolution: str,
    *,
    checkpoint: str | None = None,
    job_type: str = "image",
) -> dict:
    start_comfy()
    if not comfy_api.server_up():
        return _comfy_start_error(model_key, seed)

    try:
        workflow = load_workflow(model_key)
    except FileNotFoundError as e:
        return {"mode": "missing_workflow", "status": "error", "pass": False, "error": str(e)}

    wf = inject_params(
        workflow,
        prompt=prompt,
        seed=seed,
        resolution=resolution,
        checkpoint=checkpoint,
    )
    t0 = time.perf_counter()
    prompt_id = comfy_api.queue_prompt(wf)
    history = comfy_api.wait_for_prompt(prompt_id)
    elapsed = time.perf_counter() - t0
    outputs = comfy_api.extract_output_paths(history)
    artifact = outputs[0] if outputs else ""
    return {
        "mode": "comfyui",
        "status": "quantized",
        "model": model_key,
        "prompt": prompt[:80],
        "seed": seed,
        "resolution": resolution,
        "wall_sec": round(elapsed, 3),
        "artifact": artifact,
        "job_type": job_type,
    }


def run_image_job(
    model: str,
    prompt: str,
    seed: int,
    resolution: str = "1024x1024",
    checkpoint: str | None = None,
) -> dict:
    return _run_comfy_workflow(
        model,
        prompt,
        seed,
        resolution,
        checkpoint=checkpoint,
        job_type="image",
    )


def run_video_job(
    model: str,
    prompt: str,
    seed: int = 42,
    duration_sec: int = 5,
    resolution: str = "768x512",
    checkpoint: str | None = None,
) -> dict:
    result = _run_comfy_workflow(
        model,
        prompt,
        seed,
        resolution,
        checkpoint=checkpoint,
        job_type="video",
    )
    result["duration_sec"] = duration_sec
    if result.get("mode") == "comfyui" and result.get("wall_sec"):
        result["sec_per_clip_sec"] = round(result["wall_sec"] / max(duration_sec, 1), 3)
    return result
