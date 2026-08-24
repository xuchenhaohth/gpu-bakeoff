#!/usr/bin/env python3
"""SKU offer validation and candidate ranking for Vast.ai search/launch."""

from __future__ import annotations

import re
from typing import Any

SPARK_NAME_RE = re.compile(r"(?i)(gb10|spark|grace.?blackwell|dgx.?spark)")

SKU_GPU_PATTERNS: dict[str, re.Pattern[str]] = {
    "rtx5090_1x": re.compile(r"(?i)rtx[\s_]*5090"),
    "rtx5090_2x": re.compile(r"(?i)rtx[\s_]*5090"),
    "pro6000_1x": re.compile(r"(?i)rtx[\s_]*pro[\s_]*6000"),
    "pro6000_2x": re.compile(r"(?i)rtx[\s_]*pro[\s_]*6000"),
    "dgx_spark_gb10": SPARK_NAME_RE,
}

ARCH_ALIASES = {
    "x86_64": {"x86_64", "amd64"},
    "aarch64": {"aarch64", "arm64"},
}


def normalize_arch(arch: str) -> str:
    value = arch.lower()
    for canonical, aliases in ARCH_ALIASES.items():
        if value in aliases:
            return canonical
    return value


def ram_to_gb(value: float | int | None) -> float | None:
    """Convert Vast API ram fields (MB when >512) to GB."""
    if value is None:
        return None
    gb = float(value)
    if gb > 512:
        gb /= 1024
    return gb


def enrich_offer(offer: dict[str, Any]) -> dict[str, Any]:
    row = dict(offer)
    gpu_gb = ram_to_gb(row.get("gpu_ram"))
    cpu_gb = ram_to_gb(row.get("cpu_ram"))
    if gpu_gb is not None:
        row["gpu_ram_gb"] = round(gpu_gb, 1)
    if cpu_gb is not None:
        row["cpu_ram_gb"] = round(cpu_gb, 1)
    return row


def validate_offer(sku_id: str, offer: dict[str, Any], sku_meta: dict[str, Any]) -> str | None:
    """Return an error string when the offer does not match the SKU, else None."""
    gpu_name = offer.get("gpu_name") or ""
    pattern = SKU_GPU_PATTERNS.get(sku_id)
    if pattern and not pattern.search(gpu_name):
        return f"gpu_name {gpu_name!r} does not match {sku_id}"

    expected_gpus = sku_meta.get("num_gpus")
    if expected_gpus is not None:
        actual = offer.get("num_gpus")
        if actual is not None and int(actual) != int(expected_gpus):
            return f"num_gpus {actual} != expected {expected_gpus}"

    expected_arch = normalize_arch(sku_meta.get("arch") or "")
    if expected_arch:
        actual_arch = normalize_arch(offer.get("cpu_arch") or "")
        if actual_arch and actual_arch != expected_arch:
            return f"cpu_arch {actual_arch!r} != expected {expected_arch!r}"

    return None


def filter_valid_candidates(
    sku_id: str,
    rows: list[dict[str, Any]],
    sku_meta: dict[str, Any],
) -> list[dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    for row in rows:
        err = validate_offer(sku_id, row, sku_meta)
        if err:
            print(f"  skip id={row.get('id')}: {err}")
            continue
        valid.append(enrich_offer(row))
    return valid


def rank_candidates(rows: list[dict[str, Any]], n: int = 5) -> list[dict[str, Any]]:
    """Prefer lowest price, then highest reliability."""

    def sort_key(row: dict[str, Any]) -> tuple[float, float]:
        price = float(row.get("dph_total") or 999)
        reliability = float(row.get("reliability") or 0)
        return (price, -reliability)

    seen: set[Any] = set()
    out: list[dict[str, Any]] = []
    for row in sorted(rows, key=sort_key):
        oid = row.get("id")
        if not oid or oid in seen:
            continue
        seen.add(oid)
        out.append(row)
        if len(out) >= n:
            break
    return out


def filter_spark(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if spark_drop_reason(row) is None:
            out.append(row)
    return out


def spark_drop_reason(row: dict[str, Any]) -> str | None:
    name = row.get("gpu_name") or ""
    if not SPARK_NAME_RE.search(name):
        return f"gpu_name {name!r} does not match GB10/Spark pattern"
    arch = normalize_arch(row.get("cpu_arch") or "")
    if arch and arch != "aarch64":
        return f"cpu_arch {row.get('cpu_arch')!r} is not ARM"
    return None


def debug_spark_rows(label: str, rows: list[dict[str, Any]], sku_meta: dict[str, Any]) -> None:
    print(f"  [debug-spark] {label}: {len(rows)} raw offer(s)")
    for row in rows:
        oid = row.get("id")
        reasons: list[str] = []
        spark_reason = spark_drop_reason(row)
        if spark_reason:
            reasons.append(spark_reason)
        validate_reason = validate_offer("dgx_spark_gb10", row, sku_meta)
        if validate_reason:
            reasons.append(validate_reason)
        status = "KEEP" if not reasons else f"DROP ({'; '.join(reasons)})"
        print(
            f"    id={oid} gpu_name={row.get('gpu_name')!r} "
            f"cpu_arch={row.get('cpu_arch')!r} ${row.get('dph_total')}/hr -> {status}"
        )
