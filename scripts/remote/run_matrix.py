#!/usr/bin/env python3
"""
Matrix runner — executes Layer A/B jobs per SKU and writes results/matrix.csv.

Designed to run on each Vast instance at /workspace/bakeoff after onstart.sh.
"""

from __future__ import annotations

import csv
import os
import subprocess
import sys
from datetime import datetime, timezone

from comfy_client import run_image_job, run_video_job
from llm_client import run_llm_job
from paths import REMOTE_ROOT, RESULTS_DIR, load_config, resolve_asset
from sampler import timed_run

SKU = os.environ.get("BAKEOFF_SKU", "unknown")
RESULTS_DIR.mkdir(exist_ok=True)
(REMOTE_ROOT / "artifacts").mkdir(exist_ok=True)

IMAGE_MODELS = ["ideogram_4", "flux2_dev", "hunyuan_image_3"]
VIDEO_MODELS = ["minimax_h3", "ltx_25"]
LLM_MODELS = ["qwen38_27b", "deepseek_v4_flash"]

LAYER_B_BY_SKU = {
    "pro6000_1x": ["ltx_25", "hunyuan_image_3", "flux2_dev", "qwen38_27b"],
    "pro6000_2x": ["deepseek_v4_flash"],
}

FIELDNAMES = [
    "timestamp",
    "sku",
    "tier",
    "gpu_count",
    "memory_type",
    "layer",
    "model",
    "prompt_id",
    "precision",
    "runtime",
    "pass",
    "oom",
    "fit_status",
    "wall_sec",
    "images_per_min",
    "decode_tps",
    "prefill_tokens",
    "output_tokens",
    "peak_peak_vram_mib_max",
    "peak_peak_host_ram_used_gb",
    "peak_peak_rss_gb",
    "peak_mean_gpu_power_w",
    "peak_peak_gpu_temp_c",
    "peak_mean_cpu_pct",
    "error",
    "note",
]


def sku_meta(matrix: dict) -> dict:
    return matrix.get("skus", {}).get(SKU, {})


def should_skip_model(model_key: str, models: dict) -> tuple[bool, str]:
    spec = models.get(model_key, {})
    skip = spec.get("skip_skus") or []
    if SKU in skip:
        return True, "fail-fast SKU"
    return False, ""


def classify_fit(status: str, peak: dict, protocol: dict, job_type: str, metrics: dict) -> str:
    if status == "stub":
        return "Stub"
    if status in ("no", "error"):
        return "No"
    if metrics.get("error"):
        return "No"
    if peak.get("peak_host_ram_used_gb", 0) > 128 and SKU.startswith("rtx5090"):
        return "Offload"
    slow = protocol.get("slow_thresholds", {})
    if job_type == "image" and metrics.get("wall_sec", 0) > slow.get("image_sec", 120):
        return "Slow"
    if job_type == "video" and metrics.get("wall_sec", 0) > slow.get("video_factor", 60) * metrics.get(
        "duration_sec", 5
    ):
        return "Slow"
    if job_type == "llm" and metrics.get("decode_tps", 999) < slow.get("llm_decode_tps", 5):
        if metrics.get("status") != "stub":
            return "Slow"
    if status == "native":
        return "Native"
    return "Quantized"


def row_base(layer: str, model_key: str, prompt_id: str, precision: str, runtime: str) -> dict:
    meta = sku_meta(load_config("matrix.yaml"))
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sku": SKU,
        "tier": meta.get("tier", ""),
        "gpu_count": meta.get("num_gpus", 1),
        "memory_type": meta.get("memory_type", "discrete"),
        "layer": layer,
        "model": model_key,
        "prompt_id": prompt_id,
        "precision": precision,
        "runtime": runtime,
        "pass": True,
        "oom": False,
        "fit_status": "",
    }


def apply_peak(row: dict, peak: dict) -> None:
    for k, v in peak.items():
        if k not in ("samples", "wall_sec", "error"):
            row[f"peak_{k}"] = v


def layer_precision(spec: dict, layer: str) -> str:
    if layer == "A":
        return spec["layer_a"]["precision"]
    return spec.get("layer_b", {}).get("precision", "")


def llm_user_text(lp: dict) -> str:
    if lp.get("user_file"):
        path = resolve_asset(lp["user_file"])
        if path.exists():
            return path.read_text()
    return lp.get("user", "Say OK.")


def llm_model_id(spec: dict, layer: str) -> str:
    layer_cfg = spec["layer_a"] if layer == "A" else spec.get("layer_b", {})
    return layer_cfg.get("checkpoint") or spec.get("hf_id", "")


def resolve_gguf_path(spec: dict) -> str | None:
    file_hint = spec.get("layer_a", {}).get("file_hint")
    hf_id = spec.get("hf_id")
    if not file_hint or not hf_id:
        return None
    try:
        from huggingface_hub import hf_hub_download

        return hf_hub_download(
            repo_id=hf_id,
            filename=file_hint,
            token=os.environ.get("HF_TOKEN"),
        )
    except Exception:
        return None


def run_image_matrix(layer: str, model_key: str, models: dict, matrix: dict, writer, protocol: dict) -> None:
    spec = models[model_key]
    if layer == "B" and spec.get("layer_b", {}).get("skip"):
        return
    if layer == "B":
        lb = spec.get("layer_b", {})
        if lb.get("sku_filter") and lb["sku_filter"] != SKU:
            return

    precision = layer_precision(spec, layer)
    unified = sku_meta(matrix).get("memory_type") == "unified"
    checkpoint = spec.get("layer_a", {}).get("file_hint") or spec.get("hf_id")

    for p in matrix.get("prompts", {}).get("image", []):
        warmup = protocol.get("image_warmup", 1)
        timed = protocol.get("image_timed", 2)
        for _ in range(warmup):
            run_image_job(model_key, p["text"], seed=42, checkpoint=checkpoint)

        times: list[float] = []
        peak_summary: dict = {}
        last_job: dict = {}
        for i in range(timed):

            def job() -> None:
                nonlocal last_job
                last_job = run_image_job(model_key, p["text"], seed=100 + i, checkpoint=checkpoint)

            elapsed, peak = timed_run(job, interval=protocol.get("sampler_interval_sec", 1.5), unified=unified)
            times.append(elapsed)
            peak_summary = peak

        r = row_base(layer, model_key, p["id"], precision, spec.get("runtime", "comfyui"))
        r["wall_sec"] = round(sum(times) / len(times), 3)
        r["images_per_min"] = round(60 / r["wall_sec"], 2) if r["wall_sec"] else 0
        apply_peak(r, peak_summary)
        status = last_job.get("status", "quantized")
        r["fit_status"] = classify_fit(status, peak_summary, protocol, "image", {**r, **last_job})
        if last_job.get("error"):
            r["pass"] = False
            r["error"] = last_job["error"]
        if last_job.get("note"):
            r["note"] = last_job["note"]
        writer.writerow(r)


def run_video_matrix(layer: str, model_key: str, models: dict, matrix: dict, writer, protocol: dict) -> None:
    spec = models[model_key]
    if layer == "B" and spec.get("layer_b", {}).get("skip"):
        return
    if layer == "B":
        lb = spec.get("layer_b", {})
        if lb.get("sku_filter") and lb["sku_filter"] != SKU:
            return

    precision = layer_precision(spec, layer)
    unified = sku_meta(matrix).get("memory_type") == "unified"
    checkpoint = spec.get("layer_a", {}).get("file_hint") or spec.get("hf_id")
    prompts = matrix.get("prompts", {}).get("video", [])
    if not prompts:
        return

    vp = prompts[0]
    warmup = protocol.get("video_warmup", 1)
    timed = protocol.get("video_timed", 1)
    duration = vp.get("duration_sec", 5)

    for _ in range(warmup):
        run_video_job(model_key, vp.get("text", ""), duration_sec=duration, checkpoint=checkpoint)

    times: list[float] = []
    peak_summary: dict = {}
    last_job: dict = {}
    for i in range(timed):

        def job() -> None:
            nonlocal last_job
            last_job = run_video_job(
                model_key,
                vp.get("text", ""),
                seed=100 + i,
                duration_sec=duration,
                checkpoint=checkpoint,
            )

        elapsed, peak = timed_run(job, interval=protocol.get("sampler_interval_sec", 1.5), unified=unified)
        times.append(elapsed)
        peak_summary = peak

    r = row_base(layer, model_key, vp.get("id", "vid01"), precision, spec.get("runtime", "comfyui"))
    r["wall_sec"] = round(sum(times) / len(times), 3) if times else 0
    apply_peak(r, peak_summary)
    status = last_job.get("status", "quantized")
    metrics = {**r, **last_job, "duration_sec": duration}
    r["fit_status"] = classify_fit(status, peak_summary, protocol, "video", metrics)
    if last_job.get("error"):
        r["pass"] = False
        r["error"] = last_job["error"]
    writer.writerow(r)


def run_llm_matrix(layer: str, model_key: str, models: dict, matrix: dict, writer, protocol: dict) -> None:
    spec = models[model_key]
    skip, reason = should_skip_model(model_key, models)
    if skip:
        for key in ("short", "long"):
            lp = matrix.get("prompts", {}).get("llm", {}).get(key, {})
            if not lp:
                continue
            r = row_base(layer, model_key, lp.get("id", key), "n/a", spec.get("runtime", ""))
            r["pass"] = False
            r["fit_status"] = "No"
            r["error"] = reason
            writer.writerow(r)
        return

    if layer == "B":
        lb = spec.get("layer_b", {})
        if lb.get("sku_filter") and lb["sku_filter"] != SKU:
            if not lb.get("optional"):
                return

    precision = layer_precision(spec, layer)
    unified = sku_meta(matrix).get("memory_type") == "unified"
    runtime = spec.get("runtime", "vllm")
    model_id = llm_model_id(spec, layer)
    gguf = resolve_gguf_path(spec) if runtime == "llama_cpp" and layer == "A" else None

    llm_prompts = matrix.get("prompts", {}).get("llm", {})
    for key in ("short", "long"):
        lp = llm_prompts.get(key)
        if not lp:
            continue
        system = lp.get("system", "")
        user = llm_user_text(lp)
        max_tok = lp.get("output_tokens", 128)
        metrics: dict = {}

        def job() -> None:
            nonlocal metrics
            metrics = run_llm_job(
                runtime,
                model_id,
                system,
                user,
                max_tokens=max_tok,
                gguf_path=gguf,
            )

        elapsed, peak = timed_run(job, interval=protocol.get("sampler_interval_sec", 1.5), unified=unified)
        r = row_base(layer, model_key, lp.get("id", key), precision, runtime)
        r["wall_sec"] = round(elapsed, 3)
        r.update({k: v for k, v in metrics.items() if k not in ("pass",)})
        apply_peak(r, peak)
        if metrics.get("error"):
            r["pass"] = False
            r["fit_status"] = "No"
            r["error"] = metrics["error"]
        else:
            status = metrics.get("status", "quantized")
            r["fit_status"] = classify_fit(status, peak, protocol, "llm", metrics)
        if metrics.get("note"):
            r["note"] = metrics["note"]
        writer.writerow(r)


def run_layer(layer: str, models: dict, matrix: dict, writer, protocol: dict) -> None:
    for mk in IMAGE_MODELS:
        if mk in models:
            run_image_matrix(layer, mk, models, matrix, writer, protocol)
    for mk in VIDEO_MODELS:
        if mk in models:
            run_video_matrix(layer, mk, models, matrix, writer, protocol)
    for mk in LLM_MODELS:
        if mk in models:
            run_llm_matrix(layer, mk, models, matrix, writer, protocol)


def main() -> int:
    matrix = load_config("matrix.yaml")
    models_cfg = load_config("models.yaml")
    models = models_cfg.get("models", {})
    protocol = matrix.get("protocol", {})

    out_csv = RESULTS_DIR / "matrix.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        run_layer("A", models, matrix, writer, protocol)
        for sku_filter, model_keys in LAYER_B_BY_SKU.items():
            if SKU != sku_filter:
                continue
            for mk in model_keys:
                if mk not in models:
                    continue
                if mk in LLM_MODELS:
                    run_llm_matrix("B", mk, models, matrix, writer, protocol)
                elif mk in VIDEO_MODELS:
                    run_video_matrix("B", mk, models, matrix, writer, protocol)
                else:
                    run_image_matrix("B", mk, models, matrix, writer, protocol)

    print(f"Wrote {out_csv}")
    subprocess.run(
        [sys.executable, str(REMOTE_ROOT / "report.py"), "--csv", str(out_csv)],
        check=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
