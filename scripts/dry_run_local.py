#!/usr/bin/env python3
"""Local dry-run of matrix runner without GPU — validates CSV + report pipeline."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOTE = ROOT / "scripts" / "remote"
REMOTE_CONFIG = REMOTE / "config"
REMOTE_RESULTS = REMOTE / "results"


def cleanup() -> None:
    if REMOTE_CONFIG.exists():
        shutil.rmtree(REMOTE_CONFIG)
    if REMOTE_RESULTS.exists():
        shutil.rmtree(REMOTE_RESULTS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only-model", action="append", dest="only_models", metavar="MODEL")
    ap.add_argument("--sku", default=os.environ.get("BAKEOFF_SKU", "rtx5090_1x"))
    args = ap.parse_args()

    os.environ["BAKEOFF_SKU"] = args.sku
    if args.only_models:
        os.environ["BAKEOFF_MODELS"] = ",".join(args.only_models)
    elif os.environ.get("BAKEOFF_MODELS"):
        pass
    else:
        os.environ.pop("BAKEOFF_MODELS", None)

    cleanup()
    try:
        REMOTE_CONFIG.mkdir(parents=True)
        for name in ("matrix.yaml", "models.yaml"):
            shutil.copy(ROOT / "config" / name, REMOTE_CONFIG / name)

        subprocess.run([sys.executable, str(REMOTE / "run_matrix.py")], cwd=str(REMOTE), check=True)
        csv_path = REMOTE_RESULTS / "matrix.csv"
        subprocess.run(
            [sys.executable, str(REMOTE / "report.py"), "--csv", str(csv_path)],
            check=True,
        )
        print(f"Dry-run OK: {csv_path}")
        return 0
    finally:
        cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
