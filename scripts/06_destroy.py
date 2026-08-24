#!/usr/bin/env python3
"""Destroy all bake-off instances (-y) to stop billing."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.vast import load_dotenv, load_instances, save_instances, vastai  # noqa: E402


def main() -> int:
    load_dotenv()
    state = load_instances()
    for sku_id, rec in state.get("instances", {}).items():
        iid = rec.get("instance_id")
        if not iid or rec.get("skipped"):
            continue
        print(f"Destroy {sku_id} instance {iid}")
        vastai("destroy", "instance", str(iid), "-y", check=False)
        rec["destroyed"] = True
        rec["actual_status"] = "destroyed"
    save_instances(state)
    print("All instances destroyed — billing stopped for compute")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
