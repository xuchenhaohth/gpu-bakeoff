#!/usr/bin/env bash
# Qwen-only smoke: Spark (GGUF/llama.cpp) + RTX 5090 (vLLM), two matrix jobs per SKU.
# Env caps and SKU scope come from --preset qwen-spark-5090 (see scripts/lib/presets.py).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Qwen smoke (Spark + 5090, LLM-only) =="

uv run python scripts/01_search_offers.py
uv run python scripts/02_run_bakeoff.py --preset qwen-spark-5090
