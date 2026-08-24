#!/usr/bin/env python3
"""Poll instances until running or fail; destroy broken ones and retry backups."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.launch_instance import launch_one  # noqa: E402
from lib.sku_offers import validate_offer  # noqa: E402
from lib.vast import load_dotenv, load_instances, read_yaml, save_instances, vastai  # noqa: E402

OFFERS_PATH = ROOT / "config" / "offers.yaml"
MATRIX_PATH = ROOT / "config" / "matrix.yaml"
TIMEOUT = int(os.environ.get("WAIT_TIMEOUT_SEC", "1500"))
POLL = 15
FAIL_STATUSES = {"exited", "unknown", "offline"}


def wait_instance(instance_id: int) -> str:
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        raw = vastai("show", "instance", str(instance_id))
        inst = raw if isinstance(raw, dict) else (raw[0] if isinstance(raw, list) and raw else {})
        status = inst.get("actual_status") or inst.get("status") or "unknown"
        print(f"  instance {instance_id}: {status}")
        if status == "running":
            return "running"
        if status in FAIL_STATUSES:
            return status
        time.sleep(POLL)
    return "timeout"


def candidate_by_id(offers: dict[str, Any], sku_id: str, offer_id: Any) -> dict[str, Any] | None:
    block = offers.get("skus", {}).get(sku_id, {})
    for cand in block.get("candidates") or []:
        if cand.get("id") == offer_id:
            return cand
    return None


def retry_backups(
    sku_id: str,
    rec: dict[str, Any],
    offers: dict[str, Any],
    sku_meta: dict[str, Any],
) -> dict[str, Any] | None:
    backups = list(rec.get("backup_offer_ids") or [])
    for offer_id in backups:
        offer = candidate_by_id(offers, sku_id, offer_id)
        if not offer:
            print(f"  backup offer {offer_id} not found in {OFFERS_PATH}")
            continue
        err = validate_offer(sku_id, offer, sku_meta)
        if err:
            print(f"  skip backup {offer_id}: {err}")
            continue
        print(f"  Retrying {sku_id} with backup offer {offer_id}")
        new_rec = launch_one(sku_id, offer, sku_meta)
        if not new_rec:
            continue
        result = wait_instance(int(new_rec["instance_id"]))
        new_rec["actual_status"] = result
        if result == "running":
            new_rec["backup_offer_ids"] = [oid for oid in backups if oid != offer_id]
            return new_rec
        print(f"  Backup instance {new_rec['instance_id']} failed ({result}) — destroying")
        vastai("destroy", "instance", str(new_rec["instance_id"]), "-y", check=False)
        new_rec["destroyed"] = True
    return None


def main() -> int:
    load_dotenv()
    state = load_instances()
    instances = state.get("instances", {})
    if not instances:
        raise SystemExit("No instances in config/instances.json — run 02_launch.py")

    offers = read_yaml(OFFERS_PATH) if OFFERS_PATH.exists() else {"skus": {}}
    matrix = read_yaml(MATRIX_PATH)

    all_ok = True
    for sku_id, rec in instances.items():
        if rec.get("skipped"):
            print(f"SKIP {sku_id}: {rec.get('reason')}")
            continue
        iid = rec.get("instance_id")
        if not iid:
            continue
        print(f"Waiting {sku_id} instance {iid}...")
        result = wait_instance(int(iid))
        rec["actual_status"] = result
        if result == "running":
            continue

        print(f"  Destroying failed instance {iid}")
        vastai("destroy", "instance", str(iid), "-y", check=False)
        rec["destroyed"] = True

        sku_meta = (
            offers.get("skus", {}).get(sku_id, {}).get("sku_meta")
            or matrix.get("skus", {}).get(sku_id, {})
        )
        replacement = retry_backups(sku_id, rec, offers, sku_meta)
        if replacement:
            state["instances"][sku_id] = replacement
            print(f"  {sku_id} recovered on backup offer {replacement.get('offer_id')}")
            continue

        all_ok = False
        print(f"  No backup succeeded for {sku_id}")

    save_instances(state)
    if not all_ok:
        print("Some instances failed — fix offers and re-launch failed SKUs")
        return 1
    print("All instances running")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
