#!/usr/bin/env python3
"""Free local checks before ./scripts/smoke_qwen.sh (no Vast billing)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.presets import apply_preset  # noqa: E402
from lib.transport import use_onstart_transport  # noqa: E402
from lib.vast import ROOT as VAST_ROOT  # noqa: E402
from lib.vast import account_credit, load_dotenv, read_yaml  # noqa: E402

OFFERS_PATH = VAST_ROOT / "config" / "offers.yaml"
INSTANCES_PATH = VAST_ROOT / "config" / "instances.json"
MODELS_PATH = VAST_ROOT / "config" / "models.yaml"


def check_credit(min_credit: float) -> tuple[bool, str]:
    credit = account_credit()
    if credit < min_credit:
        return False, f"Vast credit ${credit:.2f} < MIN_CREDIT_USD={min_credit}"
    return True, f"Vast credit ${credit:.2f}"


def check_offers(skus: tuple[str, ...]) -> tuple[bool, str]:
    if not OFFERS_PATH.is_file():
        return False, f"Missing {OFFERS_PATH} — run 01_search_offers.py"
    offers = read_yaml(OFFERS_PATH)
    missing = []
    for sku in skus:
        block = offers.get("skus", {}).get(sku, {})
        cands = block.get("candidates") or []
        if not cands:
            missing.append(sku)
    if missing:
        return False, f"No offers for: {', '.join(missing)}"
    return True, f"Offers OK for {', '.join(skus)}"


def check_qwen_gguf() -> tuple[bool, str]:
    models = read_yaml(MODELS_PATH).get("models", {})
    spec = models.get("qwen38_27b", {})
    spark = (spec.get("sku_layers") or {}).get("dgx_spark_gb10", {})
    hf_id = spark.get("hf_id") or spec.get("hf_id")
    file_hint = (spark.get("layer_a") or spec.get("layer_a", {})).get("file_hint")
    if not hf_id or not file_hint:
        return False, "qwen38_27b Spark GGUF spec incomplete in models.yaml"
    try:
        from huggingface_hub import list_repo_files

        files = list_repo_files(hf_id)
        if file_hint not in files:
            return False, f"GGUF not on HF: {hf_id}/{file_hint}"
    except Exception as exc:
        return False, f"HF GGUF check failed: {exc}"
    return True, f"GGUF on HF: {hf_id}/{file_hint}"


def check_git_push() -> tuple[bool, str]:
    if not use_onstart_transport():
        return True, "SSH transport — local harness pushed (push commits before run)"
    import subprocess

    try:
        out = subprocess.run(
            ["git", "rev-list", "--count", "origin/main..HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        ahead = int((out.stdout or "0").strip() or "0")
        if ahead > 0:
            return False, f"origin/main is {ahead} commit(s) behind local — push before onstart smoke"
    except Exception as exc:
        return True, f"git ahead check skipped: {exc}"
    return True, "Git in sync with origin/main (onstart transport)"


def check_stale_instances() -> tuple[bool, str]:
    if not INSTANCES_PATH.is_file():
        return True, "No instances.json"
    try:
        data = json.loads(INSTANCES_PATH.read_text())
        instances = data.get("instances") or {}
        active = [
            sku
            for sku, rec in instances.items()
            if isinstance(rec, dict) and rec.get("instance_id") and not rec.get("skipped")
        ]
        if active:
            return False, f"Active instances in instances.json: {', '.join(active)} — run --destroy-only"
    except Exception as exc:
        return True, f"instances.json unreadable: {exc}"
    return True, "No stale instances in instances.json"


def main() -> int:
    load_dotenv()
    preset = apply_preset("qwen-spark-5090")
    for key, val in preset.get("env", {}).items():
        import os

        os.environ[key] = val

    min_credit = float(__import__("os").environ.get("MIN_CREDIT_USD", "15"))
    max_usd = float(__import__("os").environ.get("MAX_USD", "25"))
    skus = tuple(preset.get("only_sku", ()))

    checks = [
        check_credit(min_credit),
        check_offers(skus),
        check_qwen_gguf(),
        check_git_push(),
        check_stale_instances(),
    ]

    print("== smoke preflight ==")
    failed = False
    for ok, msg in checks:
        prefix = "OK " if ok else "FAIL"
        print(f"  {prefix}  {msg}")
        if not ok:
            failed = True

    print(
        f"  INFO  preset env: MIN_CREDIT_USD={min_credit} MAX_USD={max_usd} "
        f"MATRIX_TIMEOUT_SEC={__import__('os').environ.get('MATRIX_TIMEOUT_SEC')} "
        f"INSTALL_LLAMA_TIMEOUT_SEC={__import__('os').environ.get('INSTALL_LLAMA_TIMEOUT_SEC')}"
    )
    print("  INFO  Spark first run may take 30–60 min for llama.cpp build on aarch64")

    if failed:
        print("== NO-GO — fix failures before ./scripts/smoke_qwen.sh ==")
        return 1
    print(f"== GO — projected cap MAX_USD=${max_usd} ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
