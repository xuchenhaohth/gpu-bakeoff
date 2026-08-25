#!/usr/bin/env python3
"""Run presets for 02_run_bakeoff.py — env defaults and SKU/model scope."""

from __future__ import annotations

from typing import Any

PRESETS: dict[str, dict[str, Any]] = {
    "qwen-spark-5090": {
        "env": {
            "MIN_CREDIT_USD": "15",
            "MAX_USD": "25",
            "MATRIX_TIMEOUT_SEC": "7200",
            "BAKEOFF_SKIP_COMFY": "1",
            "INSTALL_LLAMA_TIMEOUT_SEC": "1800",
        },
        "only_sku": ("dgx_spark_gb10", "rtx5090_1x"),
        "only_model": ("qwen38_27b",),
        "force_sku": ("dgx_spark_gb10",),
    },
}


def apply_preset(name: str) -> dict[str, Any]:
    if name not in PRESETS:
        known = ", ".join(sorted(PRESETS))
        raise SystemExit(f"Unknown preset {name!r} — choose from: {known}")
    return PRESETS[name]


def preset_names() -> list[str]:
    return sorted(PRESETS)
