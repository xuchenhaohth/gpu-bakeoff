#!/usr/bin/env python3
"""Evidence checks for matrix.csv — Stub-only runs are not successful results."""

from __future__ import annotations

import csv
from pathlib import Path

from lib.hf_results import sku_matrix_path

EVIDENCE_STATUSES = frozenset({"Native", "Quantized", "Slow", "Offload", "No"})
RUNS_ON_STATUSES = frozenset(EVIDENCE_STATUSES - {"No"})


def read_matrix_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def has_success_evidence(rows: list[dict[str, str]]) -> bool:
    """True if any row has a successful fit (runs on), not merely No/Stub."""
    for row in rows:
        status = (row.get("fit_status") or "").strip()
        if status in RUNS_ON_STATUSES:
            return True
    return False


def has_evidence(rows: list[dict[str, str]]) -> bool:
    """True if any row has a real fit_status (not Stub / empty / ?)."""
    for row in rows:
        status = (row.get("fit_status") or "").strip()
        if status in EVIDENCE_STATUSES:
            return True
    return False


def is_stub_only(rows: list[dict[str, str]]) -> bool:
    """True when Layer A rows exist but none carry real evidence."""
    layer_a = [r for r in rows if r.get("layer") == "A"]
    if not layer_a:
        return bool(rows) and not has_evidence(rows)
    return not any((r.get("fit_status") or "").strip() in EVIDENCE_STATUSES for r in layer_a)


def verify_sku_evidence(results_root: Path, sku_id: str) -> bool:
    """Return True when pulled matrix.csv contains at least one evidence row."""
    path = sku_matrix_path(results_root, sku_id)
    return has_evidence(read_matrix_rows(path))


def verify_sku_success(results_root: Path, sku_id: str) -> bool:
    """Return True when matrix has at least one successful Layer A fit (not Stub/No only)."""
    path = sku_matrix_path(results_root, sku_id)
    rows = read_matrix_rows(path)
    if not has_success_evidence(rows):
        return False
    # LLM smoke: require measurable decode on at least one row when present
    llm_rows = [r for r in rows if r.get("layer") == "A" and r.get("runtime") in ("vllm", "llama_cpp")]
    if llm_rows and not any(float(r.get("decode_tps") or 0) > 0 for r in llm_rows):
        return False
    return True


def sku_failure_reason(results_root: Path, sku_id: str) -> str:
    """Human-readable reason when verify_sku_success is false."""
    path = sku_matrix_path(results_root, sku_id)
    rows = read_matrix_rows(path)
    if not rows:
        return "empty matrix.csv"
    if is_stub_only(rows):
        return "stub-only matrix (no real evidence)"
    if not has_success_evidence(rows):
        return "all jobs failed (fit_status=No) — check llama.log / vllm.log"
    llm_rows = [r for r in rows if r.get("layer") == "A" and r.get("runtime") in ("vllm", "llama_cpp")]
    if llm_rows and not any(float(r.get("decode_tps") or 0) > 0 for r in llm_rows):
        return "LLM jobs produced no decode throughput"
    return "matrix did not meet success criteria"
