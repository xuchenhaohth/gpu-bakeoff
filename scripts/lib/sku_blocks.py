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


def iter_scheduled_skus(
    offers: dict[str, Any],
    *,
    only_skus: set[str] | None = None,
    skip_skus: set[str] | None = None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Runnable SKUs filtered by --only-sku and --skip-sku."""
    skip = skip_skus or set()
    for sku_id, block in iter_runnable_skus(offers):
        if only_skus and sku_id not in only_skus:
            continue
        if sku_id in skip:
            continue
        yield sku_id, block


def count_scheduled_skus(
    offers: dict[str, Any],
    *,
    only_skus: set[str] | None = None,
    skip_skus: set[str] | None = None,
) -> int:
    return sum(1 for _ in iter_scheduled_skus(offers, only_skus=only_skus, skip_skus=skip_skus))
