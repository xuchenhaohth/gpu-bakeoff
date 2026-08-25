#!/usr/bin/env python3
"""Run the serial per-SKU Vast bake-off (launch → matrix → pull → destroy)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.bakeoff import run_serial  # noqa: E402
from lib.destroy import destroy_all_leftovers  # noqa: E402
from lib.presets import apply_preset, preset_names  # noqa: E402
from lib.vast import load_dotenv  # noqa: E402


def main() -> int:
    names = preset_names()
    parser = argparse.ArgumentParser(description="Serial Vast GPU bake-off")
    parser.add_argument(
        "--destroy-only",
        action="store_true",
        help="Destroy instances listed in config/instances.json and exit",
    )
    parser.add_argument(
        "--preset",
        metavar="NAME",
        help=f"Apply a run preset ({', '.join(names)})",
    )
    parser.add_argument(
        "--skip-sku",
        action="append",
        default=[],
        metavar="SKU",
        help="Skip SKU(s) even if results are missing (e.g. dgx_spark_gb10)",
    )
    parser.add_argument(
        "--only-sku",
        action="append",
        default=[],
        metavar="SKU",
        help="Run only these SKU(s); ignore others in offers.yaml",
    )
    parser.add_argument(
        "--only-model",
        action="append",
        default=[],
        metavar="MODEL",
        help="Run only these model key(s) on each SKU (e.g. qwen38_27b)",
    )
    parser.add_argument(
        "--force-sku",
        action="append",
        default=[],
        metavar="SKU",
        help="Re-run SKU(s) even when results/{sku}/matrix.csv exists",
    )
    args = parser.parse_args()

    load_dotenv()

    preset_cfg: dict[str, Any] | None = None
    if args.preset:
        preset_cfg = apply_preset(args.preset)
        for key, val in preset_cfg.get("env", {}).items():
            os.environ.setdefault(key, val)

    only_skus = list(args.only_sku)
    only_models = list(args.only_model)
    force_skus = list(args.force_sku)
    if preset_cfg:
        if not only_skus:
            only_skus = list(preset_cfg.get("only_sku", ()))
        if not only_models:
            only_models = list(preset_cfg.get("only_model", ()))
        if not force_skus:
            force_skus = list(preset_cfg.get("force_sku", ()))

    if args.destroy_only:
        return destroy_all_leftovers()
    return run_serial(
        skip_skus=set(args.skip_sku),
        only_skus=set(only_skus) if only_skus else None,
        only_models=set(only_models) if only_models else None,
        force_skus=set(force_skus),
    )


if __name__ == "__main__":
    raise SystemExit(main())
