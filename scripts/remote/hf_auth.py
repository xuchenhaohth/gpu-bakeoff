#!/usr/bin/env python3
"""Hugging Face auth for the remote harness (no scripts/lib/ on the VM)."""

from __future__ import annotations

import os
import sys


def hf_token() -> str | None:
    """Return stripped token from HF_TOKEN or HUGGING_FACE_HUB_TOKEN."""
    for key in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        tok = os.environ.get(key, "").strip()
        if tok:
            return tok
    return None


def sync_hub_token_env() -> None:
    """Ensure transformers/vLLM see HUGGING_FACE_HUB_TOKEN."""
    token = hf_token()
    if token:
        os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", token)


def login() -> bool:
    """Log in to the Hub; return False when no token is set."""
    token = hf_token()
    if not token:
        return False
    sync_hub_token_env()
    from huggingface_hub import login

    login(token=token)
    print("HF login ok")
    return True


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["login"]:
        if login():
            return 0
        print("HF_TOKEN unset — skipping login", file=sys.stderr)
        return 1
    print(f"usage: {sys.argv[0]} login", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
