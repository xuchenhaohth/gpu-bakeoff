#!/usr/bin/env python3
"""Destroy Vast bake-off instances."""

from __future__ import annotations

from typing import Any

from lib.vast import load_instances, save_instances, vastai


def destroy_instance(rec: dict[str, Any], sku_id: str = "") -> None:
    iid = rec.get("instance_id")
    if not iid or rec.get("skipped") or rec.get("destroyed"):
        return
    label = f"{sku_id} " if sku_id else ""
    print(f"Destroy {label}instance {iid}")
    vastai("destroy", "instance", str(iid), "-y", check=False)
    rec["destroyed"] = True
    rec["actual_status"] = "destroyed"


def destroy_all_leftovers() -> int:
    """Destroy any instances still recorded in config/instances.json."""
    state = load_instances()
    instances = state.get("instances", {})
    if not instances:
        return 0
    for sku_id, rec in instances.items():
        destroy_instance(rec, sku_id)
    save_instances(state)
    print("Destroyed leftover instances — billing stopped")
    return 0
