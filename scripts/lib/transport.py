#!/usr/bin/env python3
"""Bake-off transport: SSH (personal key) or onstart (team API key)."""

from __future__ import annotations

import os

TRANSPORT_SSH = "ssh"
TRANSPORT_ONSTART = "onstart"

_transport: str | None = None


def get_transport() -> str:
    global _transport
    if _transport is None:
        _transport = os.environ.get("BAKEOFF_TRANSPORT", TRANSPORT_SSH)
    return _transport


def use_onstart_transport() -> bool:
    return get_transport() == TRANSPORT_ONSTART


def set_transport(mode: str) -> None:
    global _transport
    _transport = mode
    os.environ["BAKEOFF_TRANSPORT"] = mode


def default_git_url() -> str:
    return os.environ.get(
        "BAKEOFF_GIT_URL",
        "https://github.com/xuchenhaohth/gpu-bakeoff.git",
    )


def default_git_ref() -> str:
    return os.environ.get("BAKEOFF_GIT_REF", "main")
