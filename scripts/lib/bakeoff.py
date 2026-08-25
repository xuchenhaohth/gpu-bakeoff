#!/usr/bin/env python3
"""Serial per-SKU Vast bake-off orchestration."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from lib.destroy import destroy_instance
from lib.instance_lifecycle import (
    ResumeMode,
    reconcile_bakeoff_instances,
    resolve_sku_instance,
)
from lib.matrix_poll import wait_for_matrix
from lib.pull_results import merge_results, pull_sku
from lib.push_and_run import push_and_run
from lib.sku_blocks import count_runnable_skus, iter_runnable_skus
from lib.ssh_preflight import ensure_ssh_ready
from lib.transport import get_transport, use_onstart_transport
from lib.vast import ROOT, read_yaml, save_instances, vastai
from lib.wait_running import wait_until_running

OFFERS_PATH = ROOT / "config" / "offers.yaml"
MATRIX_PATH = ROOT / "config" / "matrix.yaml"
MATRIX_TIMEOUT_SEC = int(os.environ.get("MATRIX_TIMEOUT_SEC", "28800"))
MAX_HOURS_PER_SKU = MATRIX_TIMEOUT_SEC / 3600


def format_sku_banner(
    sku_id: str,
    index: int,
    total: int,
    rec: dict[str, Any],
) -> str:
    iid = rec.get("instance_id", "?")
    dph = float(rec.get("dph_total") or 0)
    return (
        f"== SKU {sku_id} ({index}/{total}) transport={get_transport()} "
        f"instance={iid} dph=${dph:.2f}/hr =="
    )


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
    for _sku_id, block in iter_runnable_skus(offers):
        dph = float(block["candidates"][0].get("dph_total") or 0)
        total_dph += dph
        peak_dph = max(peak_dph, dph)
        count += 1
    if count == 0:
        raise SystemExit("No runnable SKUs — run 01_search_offers.py")

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
    mode: ResumeMode = "fresh",
) -> tuple[bool, dict[str, Any]]:
    """Wait, run matrix, pull results, and destroy one SKU instance."""
    if mode == "pull_only":
        iid = int(rec["instance_id"])
        try:
            pull_sku(iid, sku_id)
            return True, rec
        finally:
            destroy_instance(rec, sku_id)

    running = rec
    if mode in ("fresh", "wait"):
        waited = wait_until_running(sku_id, rec, offers, sku_meta)
        if not waited:
            if not rec.get("error"):
                rec["error"] = "never reached running"
            return False, rec
        running = waited

    iid = int(running["instance_id"])
    try:
        if mode in ("fresh", "wait", "push_and_run") and not use_onstart_transport():
            push_and_run(iid, sku_id)
        running["matrix_status"] = wait_for_matrix(iid)
        pull_via = "Hugging Face" if use_onstart_transport() else "SSH"
        print(f"  {sku_id}: matrix {running['matrix_status']} — pulling results via {pull_via}")
        pull_sku(iid, sku_id)
        return True, running
    finally:
        destroy_instance(running, sku_id)


def run_serial() -> int:
    if not OFFERS_PATH.exists():
        raise SystemExit(f"Missing {OFFERS_PATH} — run 01_search_offers.py first")

    offers = read_yaml(OFFERS_PATH)
    matrix = read_yaml(MATRIX_PATH)
    matrix_skus = matrix.get("skus", {})
    ensure_ssh_ready()
    spend_check(offers)

    state = reconcile_bakeoff_instances(matrix_skus)
    if not state.get("launched_at"):
        state["launched_at"] = datetime.now(timezone.utc).isoformat()

    attempted = 0
    succeeded = 0
    planned_total = count_runnable_skus(offers)

    for sku_id, block in offers.get("skus", {}).items():
        cands = block.get("candidates") or []
        sku_meta = block.get("sku_meta") or matrix_skus.get(sku_id, {})
        if not cands:
            if sku_id == "dgx_spark_gb10":
                print(f"Skipping {sku_id} — no offers")
                state["instances"][sku_id] = {"skipped": True, "reason": "no_gb10_offers"}
                save_instances(state)
            else:
                raise SystemExit(f"No candidates for {sku_id}")
            continue

        attempted += 1

        prev_rec = state.get("instances", {}).get(sku_id)
        rec, backup_ids, mode = resolve_sku_instance(sku_id, sku_meta, cands, prev_rec)
        if not rec:
            print(f"\n== SKU {sku_id} ({attempted}/{planned_total}) ==")
            print(f"All candidates failed validation or launch for {sku_id}")
            state["instances"][sku_id] = {"sku_id": sku_id, "error": "launch_failed"}
            save_instances(state)
            continue

        print(f"\n{format_sku_banner(sku_id, attempted, planned_total, rec)}")

        rec["backup_offer_ids"] = backup_ids
        state["instances"][sku_id] = rec
        save_instances(state)

        try:
            ok, rec = run_one_sku(sku_id, rec, offers, sku_meta, mode=mode)
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

    merge_results()
    print(f"\nSaved {ROOT / 'config' / 'instances.json'}")
    print(f"Serial run: {succeeded}/{attempted} SKUs succeeded")

    if attempted > 0 and succeeded == 0:
        return 1
    return 0
