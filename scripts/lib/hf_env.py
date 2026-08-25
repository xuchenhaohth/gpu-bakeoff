#!/usr/bin/env python3
"""Build remote .env.hf for SSH push (token via stdin, not argv)."""

from __future__ import annotations

import os

from lib.vast import hf_token

REMOTE_HF_ENV_NAME = ".env.hf"


def remote_hf_env_bytes() -> bytes:
    """Return contents for /workspace/bakeoff/.env.hf."""
    token = hf_token()
    if not token:
        raise RuntimeError("HF_TOKEN empty — cannot push remote Hugging Face auth")
    lines = [
        f"HF_TOKEN={token}",
        f"HUGGING_FACE_HUB_TOKEN={token}",
    ]
    hf_results = os.environ.get("HF_RESULTS_REPO", "").strip()
    if hf_results:
        lines.append(f"HF_RESULTS_REPO={hf_results}")
    return ("\n".join(lines) + "\n").encode()
