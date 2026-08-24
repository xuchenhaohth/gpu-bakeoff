#!/usr/bin/env python3
"""Detect, reuse, or destroy stale Vast bake-off instances."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Literal

from lib.destroy import destroy_instance
from lib.launch_instance import backup_offer_ids, launch_first_valid
from lib.matrix_poll import harness_present, matrix_done
from lib.vast import load_instances, normalize_vast_list, vastai
from lib.wait_running import FAIL_STATUSES, parse_instance_status

ResumeMode = Literal["fresh", "wait", "push_and_run", "resume_matrix", "pull_only"]

WAIT_STATUSES = frozenset({"created", "loading", "rebooting"})


def label_for_sku(sku_id: str, sku_meta: dict[str, Any]) -> str:
    return sku_meta.get("label") or f"bakeoff-{sku_id}"


def sku_for_label(label: str, matrix_skus: dict[str, Any]) -> str:
    for sku_id, meta in matrix_skus.items():
        if label_for_sku(sku_id, meta) == label:
            return sku_id
    return label


def bakeoff_labels(matrix_skus: dict[str, Any]) -> set[str]:
    return {label_for_sku(sku_id, meta) for sku_id, meta in matrix_skus.items()}


def list_account_instances() -> list[dict[str, Any]]:
    return normalize_vast_list(vastai("show", "instances"))


def classify_status(status: str | None) -> Literal["destroy", "wait", "running"]:
    if status is None or status in WAIT_STATUSES:
        return "wait"
    if status in FAIL_STATUSES:
        return "destroy"
    if status == "running":
        return "running"
    return "wait"


def api_rec_from_instance(inst: dict[str, Any], sku_id: str) -> dict[str, Any]:
    iid = inst.get("id") or inst.get("new_contract")
    return {
        "sku_id": sku_id,
        "instance_id": iid,
        "offer_id": inst.get("ask_contract_id") or inst.get("offer_id"),
        "label": inst.get("label"),
        "dph_total": inst.get("dph_total"),
        "gpu_name": inst.get("gpu_name"),
        "reliability": inst.get("reliability"),
        "actual_status": parse_instance_status(inst),
        "resumed": True,
    }


def pick_keeper(instances: list[dict[str, Any]]) -> dict[str, Any]:
    def sort_key(inst: dict[str, Any]) -> tuple[int, int]:
        status = parse_instance_status(inst)
        running_rank = 0 if status == "running" else 1
        iid = int(inst.get("id") or inst.get("new_contract") or 0)
        return (running_rank, -iid)

    return sorted(instances, key=sort_key)[0]


def find_instances_for_label(label: str) -> list[dict[str, Any]]:
    return [inst for inst in list_account_instances() if (inst.get("label") or "") == label]


def reconcile_bakeoff_instances(matrix_skus: dict[str, Any]) -> dict[str, Any]:
    """Destroy dead/duplicate bakeoff instances; load prior state."""
    state = load_instances()
    if not state.get("instances"):
        state = {
            "instances": {},
            "launched_at": datetime.now(timezone.utc).isoformat(),
        }

    labels = bakeoff_labels(matrix_skus)
    by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for inst in list_account_instances():
        label = inst.get("label") or ""
        if label in labels:
            by_label[label].append(inst)

    print("== Reconciling bakeoff instances ==")
    for label, insts in sorted(by_label.items()):
        sku_id = sku_for_label(label, matrix_skus)
        keeper = pick_keeper(insts)
        keeper_id = keeper.get("id") or keeper.get("new_contract")
        for inst in insts:
            iid = inst.get("id") or inst.get("new_contract")
            if iid != keeper_id:
                print(f"  Destroy duplicate {label} instance {iid}")
                destroy_instance(api_rec_from_instance(inst, sku_id), sku_id)

        status = parse_instance_status(keeper)
        action = classify_status(status)
        rec = api_rec_from_instance(keeper, sku_id)
        if action == "destroy":
            print(f"  Destroy stale {label} instance {keeper_id} ({status})")
            destroy_instance(rec, sku_id)
        else:
            print(f"  Keep {label} instance {keeper_id} ({status or 'provisioning'})")

    return state


def resolve_sku_instance(
    sku_id: str,
    sku_meta: dict[str, Any],
    candidates: list[dict[str, Any]],
    prev_rec: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, list[Any], ResumeMode]:
    label = label_for_sku(sku_id, sku_meta)
    matches = find_instances_for_label(label)

    if not matches and prev_rec and not prev_rec.get("destroyed"):
        prev_iid = prev_rec.get("instance_id")
        if prev_iid:
            rows = normalize_vast_list(vastai("show", "instance", str(prev_iid)))
            if rows:
                matches = [rows[0]]

    if matches:
        keeper = pick_keeper(matches)
        raw_iid = keeper.get("id") or keeper.get("new_contract")
        if raw_iid:
            iid = int(raw_iid)
            status = parse_instance_status(keeper)
            action = classify_status(status)
            rec = api_rec_from_instance(keeper, sku_id)
            backups = backup_offer_ids(candidates, rec.get("offer_id"))

            if action == "destroy":
                print(f"  Destroy failed instance {iid} ({status})")
                destroy_instance(rec, sku_id)
            elif action == "wait":
                print(f"  Reusing instance {iid} for {sku_id} — wait ({status or 'provisioning'})")
                return rec, backups, "wait"
            elif matrix_done(iid):
                print(f"  Reusing instance {iid} for {sku_id} — matrix done, pull only")
                return rec, [], "pull_only"
            elif harness_present(iid):
                print(f"  Reusing instance {iid} for {sku_id} — resume matrix")
                return rec, backups, "resume_matrix"
            else:
                print(f"  Reusing instance {iid} for {sku_id} — push harness and run")
                return rec, backups, "push_and_run"

    launched, backups = launch_first_valid(sku_id, candidates, sku_meta)
    if launched:
        return launched, backups, "fresh"
    return None, [], "fresh"


def destroy_bakeoff_api_instances(matrix_skus: dict[str, Any]) -> int:
    """Destroy all account instances with bakeoff matrix labels."""
    labels = bakeoff_labels(matrix_skus)
    destroyed = 0
    for inst in list_account_instances():
        label = inst.get("label") or ""
        if label not in labels:
            continue
        sku_id = sku_for_label(label, matrix_skus)
        destroy_instance(api_rec_from_instance(inst, sku_id), sku_id)
        destroyed += 1
    return destroyed
