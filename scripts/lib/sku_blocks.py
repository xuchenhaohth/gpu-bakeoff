#!/usr/bin/env python3
"""Shared helpers for iterating SKU blocks from offers.yaml."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


def iter_runnable_skus(offers: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield (sku_id, block) for SKUs that will run (skip GB10 when no candidates)."""
    for sku_id, block in offers.get("skus", {}).items():
        cands = block.get("candidates") or []
        if not cands and sku_id == "dgx_spark_gb10":
            continue
        if cands:
            yield sku_id, block


def count_runnable_skus(offers: dict[str, Any]) -> int:
    return sum(1 for _ in iter_runnable_skus(offers))
