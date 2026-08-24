#!/usr/bin/env python3
"""Poll instances until running or fail; destroy broken ones."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.vast import load_dotenv, load_instances, save_instances, vastai  # noqa: E402

TIMEOUT = int(__import__("os").environ.get("WAIT_TIMEOUT_SEC", "1500"))
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


def main() -> int:
    load_dotenv()
    state = load_instances()
    instances = state.get("instances", {})
    if not instances:
        raise SystemExit("No instances in config/instances.json — run 02_launch.py")

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
        if result != "running":
            all_ok = False
            print(f"  Destroying failed instance {iid}")
            vastai("destroy", "instance", str(iid), "-y", check=False)
            rec["destroyed"] = True
            backups = rec.get("backup_offer_ids") or []
            if backups:
                print(f"  Retry with backup offer {backups[0]} — re-run 02_launch.py manually for {sku_id}")

    save_instances(state)
    if not all_ok:
        print("Some instances failed — fix offers and re-launch failed SKUs")
        return 1
    print("All instances running")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
