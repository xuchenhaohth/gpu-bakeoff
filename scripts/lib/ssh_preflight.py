#!/usr/bin/env python3
"""Account SSH key checks. Team API keys cannot store keys — bake-off requires SSH."""

from __future__ import annotations

import subprocess
from typing import Any

from lib.vast import _vastai_cmd, local_ssh_identity, local_ssh_pubkey, vastai

SSH_KEYS_URL = "https://cloud.vast.ai/manage-keys/"
SSH_REQUIRED = (
    "This bake-off requires SSH. Vast has no VM password, and "
    "`vastai execute` cannot run commands on a running instance "
    "(ls/rm/du on stopped VMs only).\n"
    "Use a personal API key (not a team key) and register the local pubkey:\n"
    f"  {SSH_KEYS_URL}\n"
    '  vastai create ssh-key "$(cat ~/.ssh/id_ed25519.pub)"'
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


def ensure_ssh_ready() -> None:
    """Abort unless the local pubkey is registered on a personal Vast account."""
    pub = local_ssh_pubkey()
    if pub is None:
        raise SystemExit(
            "ERROR: No local pubkey at ~/.ssh/id_ed25519.pub (or id_rsa.pub).\n" + SSH_REQUIRED
        )
    if local_ssh_identity() is None:
        raise SystemExit(
            f"ERROR: Found {pub} but no matching private key.\n" + SSH_REQUIRED
        )
    local_blob = pubkey_blob(pub.read_text())
    if local_blob in registered_key_blobs():
        print(f"OK  Vast SSH key registered: {pub}")
        return
    ok, detail = try_register_local_key()
    if ok or local_blob in registered_key_blobs():
        print(f"OK  Vast SSH key registered: {pub}")
        return
    reason = detail.splitlines()[-1] if detail else "account has no SSH keys"
    raise SystemExit(f"ERROR: Could not register SSH key ({reason}).\n{SSH_REQUIRED}")


def attach_instance_ssh(instance_id: int) -> None:
    """Attach the local pubkey to a running instance (needed if the key was added after create)."""
    pub = local_ssh_pubkey()
    if pub is None:
        raise RuntimeError("No local SSH pubkey to attach")
    print(f"Attach SSH key {pub} -> instance {instance_id}")
    vastai("attach", "ssh", str(instance_id), str(pub), check=False)
