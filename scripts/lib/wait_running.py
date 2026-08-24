#!/usr/bin/env python3
"""Poll Vast instances until running; retry backup offers on failure."""

from __future__ import annotations

import os
import time
from typing import Any

from lib.destroy import destroy_instance
from lib.launch_instance import launch_one
from lib.sku_offers import validate_offer
from lib.vast import normalize_vast_list, vastai

TIMEOUT = int(os.environ.get("WAIT_TIMEOUT_SEC", "1500"))
POLL = 15
FAIL_STATUSES = frozenset({"exited", "unknown", "offline", "stopped"})
PROVISIONING_LABEL = "provisioning"


def status_display(status: str | None) -> str:
    if status is None:
        return PROVISIONING_LABEL
    return status


def parse_instance_status(inst: dict[str, Any]) -> str | None:
    actual = inst.get("actual_status")
    if actual is not None:
        return str(actual)
    status = inst.get("status")
    if status is not None:
        return str(status)
    return None


def instance_status(instance_id: int) -> str | None:
    raw = vastai("show", "instance", str(instance_id))
    rows = normalize_vast_list(raw)
    return parse_instance_status(rows[0] if rows else {})


def wait_instance(instance_id: int) -> str:
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        status = instance_status(instance_id)
        print(f"  instance {instance_id}: {status_display(status)}")
        if status == "running":
            return "running"
        if status is not None and status in FAIL_STATUSES:
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
    last_fail_status = rec.get("actual_status")
    last_fail_iid = rec.get("instance_id")
    for offer_id in backups:
        offer = candidate_by_id(offers, sku_id, offer_id)
        if not offer:
            print(f"  backup offer {offer_id} not found in offers.yaml")
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
        last_fail_status = result
        last_fail_iid = new_rec["instance_id"]
        if result == "running":
            new_rec["backup_offer_ids"] = [oid for oid in backups if oid != offer_id]
            return new_rec
        print(f"  Backup instance {new_rec['instance_id']} failed ({result}) — destroying")
        destroy_instance(new_rec, sku_id)
    rec["instance_id"] = last_fail_iid
    rec["actual_status"] = last_fail_status
    if last_fail_status != "running":
        rec["error"] = f"never reached running ({last_fail_status})"
    return None


def wait_until_running(
    sku_id: str,
    rec: dict[str, Any],
    offers: dict[str, Any],
    sku_meta: dict[str, Any],
) -> dict[str, Any] | None:
    """Wait for instance to run; on failure destroy and try backup offers."""
    iid = rec.get("instance_id")
    if not iid:
        return None

    print(f"Waiting {sku_id} instance {iid}...")
    result = wait_instance(int(iid))
    rec["actual_status"] = result
    if result == "running":
        return rec

    print(f"  Destroying failed instance {iid}")
    destroy_instance(rec, sku_id)

    rec["error"] = f"never reached running ({result})"
    replacement = retry_backups(sku_id, rec, offers, sku_meta)
    if replacement:
        print(f"  {sku_id} recovered on backup offer {replacement.get('offer_id')}")
    return replacement
