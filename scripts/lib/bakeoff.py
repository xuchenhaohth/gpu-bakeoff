#!/usr/bin/env python3
"""Serial per-SKU Vast bake-off orchestration."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from lib.destroy import destroy_instance
from lib.launch_instance import launch_first_valid
from lib.matrix_poll import wait_for_matrix
from lib.pull_results import merge_results, pull_sku
from lib.push_and_run import push_and_run
from lib.vast import ROOT, read_yaml, save_instances, vastai
from lib.wait_running import wait_until_running

OFFERS_PATH = ROOT / "config" / "offers.yaml"
MATRIX_PATH = ROOT / "config" / "matrix.yaml"
MATRIX_TIMEOUT_SEC = int(os.environ.get("MATRIX_TIMEOUT_SEC", "28800"))
MAX_HOURS_PER_SKU = MATRIX_TIMEOUT_SEC / 3600


def spend_check(offers: dict[str, Any]) -> None:
    max_usd = float(os.environ.get("MAX_USD", "180"))
    min_credit = float(os.environ.get("MIN_CREDIT_USD", "50"))
    user = vastai("show", "user")
    credit = float(user.get("credit") or user.get("balance") or 0)
    if credit <= 0:
        raise SystemExit(
            f"Insufficient credit (${credit:.2f}). "
            "Add funds at https://cloud.vast.ai/billing/"
        )
    if credit < min_credit:
        raise SystemExit(f"Insufficient credit ${credit:.2f} < MIN_CREDIT_USD={min_credit}")

    total_dph = 0.0
    peak_dph = 0.0
    count = 0
    for sku, block in offers.get("skus", {}).items():
        cands = block.get("candidates") or []
        if not cands and sku == "dgx_spark_gb10":
            continue
        if not cands:
            raise SystemExit(f"No candidates for {sku} — run 01_search_offers.py")
        dph = float(cands[0].get("dph_total") or 0)
        total_dph += dph
        peak_dph = max(peak_dph, dph)
        count += 1
    projected = total_dph * MAX_HOURS_PER_SKU
    print(
        f"Credit: ${credit:.2f} | {count} SKUs serial × {MAX_HOURS_PER_SKU:.1f}h "
        f"projected: ${projected:.2f} (cap ${max_usd}) | peak concurrent ${peak_dph:.2f}/hr"
    )
    if projected > max_usd:
        raise SystemExit(f"Projected spend ${projected:.2f} exceeds MAX_USD={max_usd}")


def run_one_sku(
    sku_id: str,
    rec: dict[str, Any],
    offers: dict[str, Any],
    sku_meta: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    """Wait, run matrix, pull results, and destroy one SKU instance."""
    running = wait_until_running(sku_id, rec, offers, sku_meta)
    if not running:
        rec["error"] = "never reached running"
        return False, rec

    iid = int(running["instance_id"])
    try:
        push_and_run(iid, sku_id)
        running["matrix_status"] = wait_for_matrix(iid)
        pull_sku(iid, sku_id)
        return True, running
    finally:
        destroy_instance(running, sku_id)


def run_serial() -> int:
    if not OFFERS_PATH.exists():
        raise SystemExit(f"Missing {OFFERS_PATH} — run 01_search_offers.py first")

    offers = read_yaml(OFFERS_PATH)
    matrix = read_yaml(MATRIX_PATH)
    spend_check(offers)

    state: dict[str, Any] = {
        "instances": {},
        "launched_at": datetime.now(timezone.utc).isoformat(),
    }

    attempted = 0
    succeeded = 0

    for sku_id, block in offers.get("skus", {}).items():
        cands = block.get("candidates") or []
        sku_meta = block.get("sku_meta") or matrix.get("skus", {}).get(sku_id, {})
        if not cands:
            if sku_id == "dgx_spark_gb10":
                print(f"Skipping {sku_id} — no offers")
                state["instances"][sku_id] = {"skipped": True, "reason": "no_gb10_offers"}
                save_instances(state)
            else:
                raise SystemExit(f"No candidates for {sku_id}")
            continue

        attempted += 1
        print(f"\n== SKU {sku_id} ({attempted}) ==")

        rec, backup_ids = launch_first_valid(sku_id, cands, sku_meta)
        if not rec:
            print(f"All candidates failed validation or launch for {sku_id}")
            state["instances"][sku_id] = {"sku_id": sku_id, "error": "launch_failed"}
            save_instances(state)
            continue

        rec["backup_offer_ids"] = backup_ids
        try:
            ok, rec = run_one_sku(sku_id, rec, offers, sku_meta)
            if ok:
                succeeded += 1
            else:
                print(f"  {sku_id} failed before matrix could run")
        except KeyboardInterrupt:
            destroy_instance(rec, sku_id)
            state["instances"][sku_id] = rec
            save_instances(state)
            raise

        state["instances"][sku_id] = rec
        save_instances(state)
        print(f"  {sku_id} complete — destroyed instance {rec.get('instance_id')}")

    merge_results()
    print(f"\nSaved {ROOT / 'config' / 'instances.json'}")
    print(f"Serial run: {succeeded}/{attempted} SKUs succeeded")

    if attempted > 0 and succeeded == 0:
        return 1
    return 0
