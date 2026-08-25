#!/usr/bin/env python3
"""Destroy Vast bake-off instances."""

from __future__ import annotations

from typing import Any

from lib.vast import ROOT, account_credit, load_instances, read_yaml, save_instances, vastai


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
    """Destroy bakeoff instances from config/instances.json and API label scan."""
    state = load_instances()
    instances = state.get("instances", {})
    for sku_id, rec in instances.items():
        destroy_instance(rec, sku_id)

    matrix_path = ROOT / "config" / "matrix.yaml"
    matrix_skus = read_yaml(matrix_path).get("skus", {}) if matrix_path.exists() else {}
    from lib.instance_lifecycle import destroy_bakeoff_api_instances

    api_destroyed = destroy_bakeoff_api_instances(matrix_skus)

    save_instances(state)
    print(
        f"Destroyed leftover instances ({len(instances)} in json, "
        f"{api_destroyed} from API scan) — billing stopped"
    )
    try:
        credit = account_credit()
        print(f"Credit: ${credit:.2f}")
    except RuntimeError as exc:
        print(f"Warning: could not fetch account credit: {exc}")
    return 0
