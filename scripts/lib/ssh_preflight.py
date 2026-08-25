#!/usr/bin/env python3
"""Account SSH key checks; team API keys use onstart transport instead."""

from __future__ import annotations

import subprocess
from typing import Any

from lib.transport import TRANSPORT_ONSTART, TRANSPORT_SSH, set_transport
from lib.vast import _vastai_cmd, local_ssh_identity, local_ssh_pubkey, vastai

SSH_KEYS_URL = "https://cloud.vast.ai/manage-keys/"
ONSTART_NOTE = (
    "Team API key detected — using onstart transport:\n"
    "  • Harness clones from public git at VM boot (--onstart)\n"
    "  • Progress via vastai logs ([progress] lines)\n"
    "  • Results pulled from Hugging Face (HF_TOKEN)\n"
    "For SSH/rsync instead, use a personal API key and register:\n"
    f"  {SSH_KEYS_URL}"
)


def pubkey_blob(line: str) -> str:
    """Return the key material field from an OpenSSH public key line."""
    parts = line.strip().split()
    if len(parts) >= 2:
        return parts[1]
    return line.strip()


def _walk_key_blobs(obj: Any) -> list[str]:
    blobs: list[str] = []
    if isinstance(obj, str):
        stripped = obj.strip()
        if stripped.startswith("ssh-") or "AAAA" in stripped:
            blobs.append(pubkey_blob(stripped))
    elif isinstance(obj, dict):
        for value in obj.values():
            blobs.extend(_walk_key_blobs(value))
    elif isinstance(obj, list):
        for value in obj:
            blobs.extend(_walk_key_blobs(value))
    return blobs


def registered_key_blobs() -> list[str]:
    raw = vastai("show", "ssh-keys", check=False)
    return _walk_key_blobs(raw)


def _redact(text: str, secret: str) -> str:
    if not secret:
        return text
    out = text.replace(secret, "<pubkey>")
    blob = pubkey_blob(secret)
    if blob:
        out = out.replace(blob, "<blob>")
    return out


def try_register_local_key() -> tuple[bool, str]:
    pub = local_ssh_pubkey()
    if pub is None:
        return False, "no local pubkey"
    text = pub.read_text().strip()
    proc = subprocess.run(
        _vastai_cmd("create", "ssh-key", text, raw=False),
        capture_output=True,
        text=True,
    )
    combined = _redact(f"{proc.stdout}\n{proc.stderr}".strip(), text)
    if pubkey_blob(text) in registered_key_blobs():
        return True, combined
    return False, combined or f"create ssh-key exit {proc.returncode}"


def _ssh_registered() -> bool:
    pub = local_ssh_pubkey()
    if pub is None or local_ssh_identity() is None:
        return False
    local_blob = pubkey_blob(pub.read_text())
    return local_blob in registered_key_blobs()


def ensure_ssh_ready() -> None:
    """Select SSH transport when keys work; otherwise onstart (team API keys)."""
    pub = local_ssh_pubkey()
    if pub is not None and local_ssh_identity() is not None:
        if _ssh_registered():
            set_transport(TRANSPORT_SSH)
            print(f"OK  Vast SSH key registered: {pub}")
            return
        ok, _detail = try_register_local_key()
        if ok or _ssh_registered():
            set_transport(TRANSPORT_SSH)
            print(f"OK  Vast SSH key registered: {pub}")
            return

    set_transport(TRANSPORT_ONSTART)
    print(f"WARN: {ONSTART_NOTE}")


def attach_instance_ssh(instance_id: int) -> None:
    """Attach the local pubkey to a running instance (SSH transport only)."""
    from lib.transport import use_onstart_transport

    if use_onstart_transport():
        return
    pub = local_ssh_pubkey()
    if pub is None:
        raise RuntimeError("No local SSH pubkey to attach")
    print(f"Attach SSH key {pub} -> instance {instance_id}")
    vastai("attach", "ssh", str(instance_id), str(pub), check=False)
