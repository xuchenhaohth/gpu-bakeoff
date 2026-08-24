#!/usr/bin/env python3
"""Search Vast.ai offers and write config/offers.yaml with ranked candidates."""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.vast import load_dotenv, read_yaml, vastai, write_yaml  # noqa: E402

OFFERS_PATH = ROOT / "config" / "offers.yaml"
MATRIX_PATH = ROOT / "config" / "matrix.yaml"

SPARK_NAME_RE = re.compile(r"(?i)(gb10|spark|grace.?blackwell|dgx.?spark)")


def normalize_offers(raw) -> list[dict]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        if "offers" in raw:
            return raw["offers"]
        return [raw]
    return []


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


def filter_spark(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        name = r.get("gpu_name") or ""
        ram = float(r.get("gpu_ram") or 0)
        if SPARK_NAME_RE.search(name) or ram >= 120:
            out.append(r)
    return out


def top_candidates(rows: list[dict], n: int = 5) -> list[dict]:
    seen = set()
    out = []
    for r in sorted(rows, key=lambda x: float(x.get("dph_total") or 999)):
        oid = r["id"]
        if oid in seen:
            continue
        seen.add(oid)
        out.append(r)
        if len(out) >= n:
            break
    return out


def main() -> int:
    load_dotenv()
    matrix = read_yaml(MATRIX_PATH)
    sku_defs = matrix.get("skus", {})

    template = {
        "rtx5090_1x": "num_gpus=1 gpu_ram>=31 gpu_ram<=33 verified=true rentable=true direct_port_count>=1 cpu_ram>=128 reliability>=0.98",
        "rtx5090_2x": "num_gpus=2 gpu_ram>=31 gpu_ram<=33 verified=true rentable=true direct_port_count>=1 cpu_ram>=128 reliability>=0.98",
        "pro6000_1x": "num_gpus=1 gpu_ram>=90 gpu_ram<=100 verified=true rentable=true direct_port_count>=1 cpu_ram>=256 reliability>=0.98",
        "pro6000_2x": "num_gpus=2 gpu_ram>=90 gpu_ram<=100 verified=true rentable=true direct_port_count>=1 cpu_ram>=256 reliability>=0.98",
        "dgx_spark_gb10": "gpu_ram>=120 verified=true rentable=true direct_port_count>=1",
    }

    out: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "skus": {},
    }

    for sku_id, query in template.items():
        print(f"Searching {sku_id}: {query}")
        rows = search(query, no_default=(sku_id == "dgx_spark_gb10"))
        if sku_id == "dgx_spark_gb10":
            rows = filter_spark(rows)
            if not rows:
                print("  WARNING: no GB10/Spark offers — Spark column will be 'no rental today'")
        candidates = top_candidates(rows, 5)
        for c in candidates:
            print(
                f"  - id={c['id']} {c.get('gpu_name')} "
                f"${c.get('dph_total')}/hr ram={c.get('gpu_ram')}GB "
                f"cpu_ram={c.get('cpu_ram')}GB {c.get('geolocation')}"
            )
        out["skus"][sku_id] = {
            "search_query": query,
            "sku_meta": sku_defs.get(sku_id, {}),
            "candidates": candidates,
        }

    write_yaml(OFFERS_PATH, out)
    print(f"Wrote {OFFERS_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
