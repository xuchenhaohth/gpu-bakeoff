#!/usr/bin/env python3
"""Run the serial per-SKU Vast bake-off (launch → matrix → pull → destroy)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.bakeoff import run_serial  # noqa: E402
from lib.destroy import destroy_all_leftovers  # noqa: E402
from lib.vast import load_dotenv  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Serial Vast GPU bake-off")
    parser.add_argument(
        "--destroy-only",
        action="store_true",
        help="Destroy instances listed in config/instances.json and exit",
    )
    parser.add_argument(
        "--skip-sku",
        action="append",
        default=[],
        metavar="SKU",
        help="Skip SKU(s) even if results are missing (e.g. dgx_spark_gb10)",
    )
    args = parser.parse_args()

    load_dotenv()
    if args.destroy_only:
        return destroy_all_leftovers()
    return run_serial(skip_skus=set(args.skip_sku))


if __name__ == "__main__":
    raise SystemExit(main())
