"""Model selection, SKU-specific overrides, and job counting for matrix runs."""

from __future__ import annotations

import copy
import os
from typing import Any

IMAGE_MODELS = ["ideogram_4", "flux2_dev", "hunyuan_image_3"]
VIDEO_MODELS = ["minimax_h3"]
LLM_MODELS = ["qwen38_27b", "deepseek_v4_flash"]


def bakeoff_models_filter() -> set[str] | None:
    raw = os.environ.get("BAKEOFF_MODELS", "").strip()
    if not raw:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


def model_selected(model_key: str) -> bool:
    filt = bakeoff_models_filter()
    if filt is None:
        return True
    return model_key in filt


def resolve_model_spec(base_spec: dict[str, Any], sku: str) -> dict[str, Any]:
    """Merge sku_layers[sku] over the base models.yaml entry."""
    spec = copy.deepcopy(base_spec)
    override = (base_spec.get("sku_layers") or {}).get(sku, {})
    for field in ("runtime", "hf_id", "disk_gb"):
        if field in override:
            spec[field] = override[field]
    if "layer_a" in override:
        spec["layer_a"] = {**spec.get("layer_a", {}), **override["layer_a"]}
    if "llama_extra_args" in override:
        spec["llama_extra_args"] = list(override["llama_extra_args"])
    return spec


def active_image_models(models: dict[str, Any]) -> list[str]:
    return [mk for mk in IMAGE_MODELS if mk in models and model_selected(mk)]


def active_video_models(models: dict[str, Any]) -> list[str]:
    return [mk for mk in VIDEO_MODELS if mk in models and model_selected(mk)]


def active_llm_models(models: dict[str, Any]) -> list[str]:
    return [mk for mk in LLM_MODELS if mk in models and model_selected(mk)]


def _llm_job_count(model_key: str, models: dict[str, Any], matrix: dict[str, Any], sku: str) -> int:
    base = models.get(model_key, {})
    if not base:
        return 0
    skip_skus = base.get("skip_skus") or []
    if sku in skip_skus:
        return 2  # skip rows still written for short + long
    llm_prompts = matrix.get("prompts", {}).get("llm", {})
    count = 0
    for key in ("short", "long"):
        if llm_prompts.get(key):
            count += 1
    return count


def compute_job_total(models: dict[str, Any], matrix: dict[str, Any], sku: str) -> int:
    total = 0
    image_prompts = matrix.get("prompts", {}).get("image", [])
    for mk in active_image_models(models):
        total += len(image_prompts)
    if active_video_models(models) and matrix.get("prompts", {}).get("video"):
        total += 1
    for mk in active_llm_models(models):
        total += _llm_job_count(mk, models, matrix, sku)
    return max(total, 1)
