#!/usr/bin/env python3
"""Copy remote harness to instances and start the matrix runner."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.vast import load_dotenv, load_instances, vastai_copy, vastai_execute  # noqa: E402

REMOTE_DIR = ROOT / "scripts" / "remote"
CONFIG_DIR = ROOT / "config"


def copy_to(instance_id: int, local: Path, remote: str) -> None:
    src = f"local:{local}/"
    dst = f"{instance_id}:{remote}"
    print(f"Copy {src} -> {dst}")
    vastai_copy(src, dst)


def execute(instance_id: int, cmd: str) -> None:
    print(f"Execute on {instance_id}: {cmd[:80]}...")
    vastai_execute(instance_id, cmd)


def main() -> int:
    load_dotenv()
    state = load_instances()
    for sku_id, rec in state.get("instances", {}).items():
        if rec.get("skipped") or rec.get("destroyed"):
            continue
        if rec.get("actual_status") != "running":
            print(f"Skip {sku_id}: not running")
            continue
        iid = int(rec["instance_id"])
        copy_to(iid, REMOTE_DIR, "/workspace/bakeoff/")
        copy_to(iid, CONFIG_DIR, "/workspace/bakeoff/config/")
        execute(
            iid,
            "chmod +x /workspace/bakeoff/onstart.sh /workspace/bakeoff/install_stack.sh && "
            "cd /workspace/bakeoff && "
            "nohup bash -lc './onstart.sh && python3 run_matrix.py' "
            ">/workspace/bakeoff/run.log 2>&1 &",
        )
        print(f"Started matrix on {sku_id} (instance {iid}) — tail: vastai logs {iid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
