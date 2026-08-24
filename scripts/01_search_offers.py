#!/usr/bin/env python3
"""Search Vast.ai offers and write config/offers.yaml with ranked candidates."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.sku_offers import (  # noqa: E402
    debug_spark_rows,
    filter_spark,
    filter_valid_candidates,
    ram_to_gb,
    rank_candidates,
)
from lib.vast import load_dotenv, normalize_vast_list, read_yaml, vastai, write_yaml  # noqa: E402

OFFERS_PATH = ROOT / "config" / "offers.yaml"
MATRIX_PATH = ROOT / "config" / "matrix.yaml"
SPARK_FALLBACK_QUERY = "cpu_arch=arm64 num_gpus=1 rentable=true direct_port_count>=1"


def normalize_offers(raw) -> list[dict]:
    return normalize_vast_list(raw, "offers")


def offer_row(o: dict) -> dict:
    gpu_name = o.get("gpu_name") or o.get("gpuName") or ""
    return {
        "id": o.get("id") or o.get("ask_contract_id"),
        "gpu_name": gpu_name,
        "num_gpus": o.get("num_gpus"),
        "gpu_ram": o.get("gpu_ram"),
        "cpu_ram": o.get("cpu_ram"),
        "dph_total": o.get("dph_total"),
        "reliability": o.get("reliability"),
        "geolocation": o.get("geolocation"),
        "cuda_max_good": o.get("cuda_max_good"),
        "compute_cap": o.get("compute_cap"),
        "cpu_arch": o.get("cpu_arch") or o.get("arch"),
        "image": o.get("image") or o.get("image_runtype"),
        "rentable": o.get("rentable"),
        "verified": o.get("verified"),
        "inet_down": o.get("inet_down"),
        "disk_space": o.get("disk_space"),
    }


def search(query: str, no_default: bool = False) -> list[dict]:
    args = ["search", "offers", query, "-o", "dph_total+"]
    if no_default:
        args.insert(2, "--no-default")
    raw = vastai(*args, check=False)
    rows = [offer_row(o) for o in normalize_offers(raw)]
    return [r for r in rows if r.get("id") and r.get("rentable") is not False]


def fmt_ram_gb(value: float | int | None) -> str:
    gb = ram_to_gb(value)
    return "?" if gb is None else f"{gb:.0f}"


def search_spark(sku_meta: dict[str, Any], query: str, debug_spark: bool) -> list[dict]:
    print(f"Searching dgx_spark_gb10: {query}")
    rows = search(query, no_default=True)
    if debug_spark:
        debug_spark_rows("primary", rows, sku_meta)
    rows = filter_spark(rows)
    if not rows:
        print("  Retrying Spark search with relaxed ARM fallback...")
        fallback_rows = search(SPARK_FALLBACK_QUERY, no_default=True)
        if debug_spark:
            debug_spark_rows("fallback", fallback_rows, sku_meta)
        rows = filter_spark(fallback_rows)
    if not rows:
        print("  WARNING: no GB10/Spark offers — Spark column will be 'no rental today'")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Search Vast.ai offers for bake-off SKUs")
    parser.add_argument(
        "--debug-spark",
        action="store_true",
        help="Print why GB10/Spark offers are kept or dropped",
    )
    args = parser.parse_args()

    load_dotenv()
    matrix = read_yaml(MATRIX_PATH)
    sku_defs = matrix.get("skus", {})

    template = {
        "dgx_spark_gb10": (
            "cpu_arch=arm64 num_gpus=1 gpu_ram>=115 gpu_ram<=125 verified=true "
            "rentable=true direct_port_count>=1"
        ),
        "rtx5090_1x": (
            "gpu_name=RTX_5090 num_gpus=1 gpu_ram>=31 gpu_ram<=33 verified=true "
            "rentable=true direct_port_count>=1 cpu_ram>=128 reliability>=0.98"
        ),
        "rtx5090_2x": (
            "gpu_name=RTX_5090 num_gpus=2 gpu_ram>=31 gpu_ram<=33 verified=true "
            "rentable=true direct_port_count>=1 cpu_ram>=128 reliability>=0.98"
        ),
        "pro6000_1x": (
            "gpu_name in [RTX_PRO_6000_WS,RTX_PRO_6000,RTX_PRO_6000_BLACKWELL_SERVER_EDITION] "
            "num_gpus=1 gpu_ram>=90 gpu_ram<=100 verified=true rentable=true "
            "direct_port_count>=1 cpu_ram>=256 reliability>=0.98"
        ),
        "pro6000_2x": (
            "gpu_name in [RTX_PRO_6000_WS,RTX_PRO_6000,RTX_PRO_6000_BLACKWELL_SERVER_EDITION] "
            "num_gpus=2 gpu_ram>=90 gpu_ram<=100 verified=true rentable=true "
            "direct_port_count>=1 cpu_ram>=256 reliability>=0.98"
        ),
    }

    out: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "skus": {},
    }

    for sku_id, query in template.items():
        sku_meta = sku_defs.get(sku_id, {})
        if sku_id == "dgx_spark_gb10":
            rows = search_spark(sku_meta, query, args.debug_spark)
        else:
            print(f"Searching {sku_id}: {query}")
            rows = search(query, no_default=False)
        rows = filter_valid_candidates(sku_id, rows, sku_meta)
        candidates = rank_candidates(rows, 5)
        for c in candidates:
            rel = c.get("reliability")
            rel_s = f" rel={float(rel):.3f}" if rel is not None else ""
            print(
                f"  - id={c['id']} {c.get('gpu_name')} "
                f"${c.get('dph_total')}/hr ram={fmt_ram_gb(c.get('gpu_ram'))}GB "
                f"cpu_ram={fmt_ram_gb(c.get('cpu_ram'))}GB{rel_s} {c.get('geolocation')}"
            )
        out["skus"][sku_id] = {
            "search_query": query,
            "sku_meta": sku_meta,
            "candidates": candidates,
        }

    write_yaml(OFFERS_PATH, out)
    print(f"Wrote {OFFERS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
