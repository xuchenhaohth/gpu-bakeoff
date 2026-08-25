#!/usr/bin/env python3
"""ComfyUI diffusion job client."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import comfy_api
from workflow_loader import inject_params, load_workflow

COMFY_PORT = int(__import__("os").environ.get("COMFY_PORT", "8188"))
COMFY_DIR = Path("/workspace/ComfyUI")
COMFY_LOG = Path("/workspace/bakeoff/comfy.log")


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
        for _ in range(60):
            if comfy_api.server_up():
                return
            time.sleep(2)


def _gpu_warmup_stub(model: str, seed: int) -> dict:
    try:
        subprocess.run(
            [
                "python3",
                "-c",
                "import torch; "
                "assert torch.cuda.is_available(); "
                "x=torch.randn(4096,4096,device='cuda'); (x@x).sum().item()",
            ],
            check=False,
            capture_output=True,
            timeout=60,
        )
    except Exception:
        time.sleep(0.2)
    else:
        time.sleep(0.2)
    return {"mode": "gpu_stub", "status": "stub", "model": model, "seed": seed}


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
        return _gpu_warmup_stub(model_key, seed)

    try:
        workflow = load_workflow(model_key)
    except FileNotFoundError as e:
        return {"mode": "missing_workflow", "status": "error", "error": str(e)}

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
