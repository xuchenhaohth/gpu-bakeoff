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

from lib.launch_instance import launch_one  # noqa: E402
from lib.sku_offers import validate_offer  # noqa: E402
from lib.vast import load_dotenv, read_yaml, save_instances, vastai  # noqa: E402

OFFERS_PATH = ROOT / "config" / "offers.yaml"
MATRIX_PATH = ROOT / "config" / "matrix.yaml"
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


def launch_first_valid(
    sku_id: str,
    candidates: list[dict[str, Any]],
    sku_meta: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[Any]]:
    for i, offer in enumerate(candidates):
        err = validate_offer(sku_id, offer, sku_meta)
        if err:
            print(f"  skip candidate {offer.get('id')}: {err}")
            continue
        rec = launch_one(sku_id, offer, sku_meta)
        if rec:
            backup_ids = [c["id"] for c in candidates[i + 1 : i + 4]]
            return rec, backup_ids
    return None, []


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
        rec, backup_ids = launch_first_valid(sku_id, cands, sku_meta)
        if not rec:
            raise SystemExit(f"All candidates failed validation or launch for {sku_id}")
        rec["backup_offer_ids"] = backup_ids
        state["instances"][sku_id] = rec

    save_instances(state)
    print(f"Saved {ROOT / 'config' / 'instances.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
