#!/usr/bin/env python3
"""Launch on-demand Vast instances for each SKU with a valid offer candidate."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.vast import load_dotenv, read_yaml, save_instances, vastai  # noqa: E402

OFFERS_PATH = ROOT / "config" / "offers.yaml"
MATRIX_PATH = ROOT / "config" / "matrix.yaml"
DISK_GB = int(os.environ.get("DISK_GB", "400"))
RUN_HOURS = 24


def spend_check(offers: dict[str, Any]) -> None:
    max_usd = float(os.environ.get("MAX_USD", "180"))
    min_credit = float(os.environ.get("MIN_CREDIT_USD", "50"))
    user = vastai("show", "user")
    credit = float(user.get("credit") or user.get("balance") or 0)
    if credit < min_credit:
        raise SystemExit(f"Insufficient credit ${credit:.2f} < MIN_CREDIT_USD={min_credit}")

    total_dph = 0.0
    count = 0
    for sku, block in offers.get("skus", {}).items():
        cands = block.get("candidates") or []
        if not cands and sku == "dgx_spark_gb10":
            continue
        if not cands:
            raise SystemExit(f"No candidates for {sku} — run 01_search_offers.py")
        total_dph += float(cands[0].get("dph_total") or 0)
        count += 1
    projected = total_dph * RUN_HOURS
    print(
        f"Credit: ${credit:.2f} | {count} instances × {RUN_HOURS}h "
        f"projected: ${projected:.2f} (cap ${max_usd})"
    )
    if projected > max_usd:
        raise SystemExit(f"Projected spend ${projected:.2f} exceeds MAX_USD={max_usd}")


def resolve_image(sku_id: str, offer: dict, sku_meta: dict) -> str:
    arch = sku_meta.get("arch") or offer.get("cpu_arch") or "x86_64"
    image = sku_meta.get("image") or offer.get("image")
    if not image:
        if arch == "aarch64":
            raise SystemExit(
                f"No container image for aarch64 SKU {sku_id} — "
                "re-run 01_search_offers.py or set image in matrix.yaml"
            )
        image = "vastai/pytorch:@vastai-automatic-tag"
    return image


def launch_one(sku_id: str, offer: dict, sku_meta: dict) -> dict | None:
    offer_id = offer["id"]
    label = sku_meta.get("label") or f"bakeoff-{sku_id}"
    image = resolve_image(sku_id, offer, sku_meta)

    hf = os.environ.get("HF_TOKEN", "")
    tz = os.environ.get("TZ", "Australia/Melbourne")
    env_str = f"-e HF_TOKEN={hf} -e TZ={tz} -e BAKEOFF_SKU={sku_id}"

    print(f"Launching {sku_id} offer={offer_id} label={label} image={image}")
    result = vastai(
        "create",
        "instance",
        str(offer_id),
        "--image",
        image,
        "--disk",
        str(DISK_GB),
        "--ssh",
        "--direct",
        "--label",
        label,
        "--env",
        env_str,
    )
    if isinstance(result, dict) and result.get("success"):
        iid = result.get("new_contract") or result.get("id")
        print(f"  -> instance id {iid}")
        return {
            "sku_id": sku_id,
            "instance_id": iid,
            "offer_id": offer_id,
            "label": label,
            "image": image,
            "dph_total": offer.get("dph_total"),
            "gpu_name": offer.get("gpu_name"),
            "status": "created",
        }
    print(f"  FAILED: {result}")
    return None


def main() -> int:
    load_dotenv()
    if not OFFERS_PATH.exists():
        raise SystemExit(f"Missing {OFFERS_PATH} — run 01_search_offers.py first")

    offers = read_yaml(OFFERS_PATH)
    matrix = read_yaml(MATRIX_PATH)
    spend_check(offers)

    state: dict[str, Any] = {"instances": {}, "launched_at": datetime.now(timezone.utc).isoformat()}

    for sku_id, block in offers.get("skus", {}).items():
        cands = block.get("candidates") or []
        sku_meta = block.get("sku_meta") or matrix.get("skus", {}).get(sku_id, {})
        if not cands:
            if sku_id == "dgx_spark_gb10":
                print(f"Skipping {sku_id} — no offers")
                state["instances"][sku_id] = {"skipped": True, "reason": "no_gb10_offers"}
            else:
                raise SystemExit(f"No candidates for {sku_id}")
            continue
        rec = launch_one(sku_id, cands[0], sku_meta)
        if rec:
            rec["backup_offer_ids"] = [c["id"] for c in cands[1:4]]
            state["instances"][sku_id] = rec

    save_instances(state)
    print(f"Saved {ROOT / 'config' / 'instances.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
