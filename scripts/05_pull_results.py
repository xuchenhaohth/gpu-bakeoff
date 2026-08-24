#!/usr/bin/env python3
"""Pull results from running/completed instances."""

from __future__ import annotations

import csv
import subprocess
import sys
from glob import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.vast import load_dotenv, load_instances, vastai_copy  # noqa: E402

RESULTS = ROOT / "results"


def pull(instance_id: int, remote: str, local: Path) -> None:
    local.mkdir(parents=True, exist_ok=True)
    src = f"{instance_id}:{remote}"
    dst = f"local:{local}/"
    print(f"Pull {src} -> {dst}")
    vastai_copy(src, dst, check=False)


def main() -> int:
    load_dotenv()
    state = load_instances()
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "artifacts").mkdir(exist_ok=True)

    for sku_id, rec in state.get("instances", {}).items():
        if rec.get("skipped"):
            continue
        iid = rec.get("instance_id")
        if not iid:
            continue
        sku_dir = RESULTS / sku_id
        pull(int(iid), "/workspace/bakeoff/results/", sku_dir)
        pull(int(iid), "/workspace/bakeoff/run.log", sku_dir / "run.log")

    merged = RESULTS / "matrix.csv"
    header = None
    rows = []
    for path in glob(str(RESULTS / "*/matrix.csv")):
        with open(path, newline="") as f:
            r = csv.DictReader(f)
            if header is None:
                header = r.fieldnames
            rows.extend(list(r))
    if header and rows:
        with open(merged, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(rows)
        print(f"Merged {len(rows)} rows -> {merged}")
        report_html = RESULTS / "report.html"
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "remote" / "report.py"),
                "--csv",
                str(merged),
                "--html",
                str(report_html),
                "--update-docs",
            ],
            check=False,
        )
    else:
        print("No matrix.csv files found yet — matrix may still be running")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
