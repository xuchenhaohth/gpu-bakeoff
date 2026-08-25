#!/usr/bin/env python3
"""Poll Vast instances until running; retry backup offers on failure."""

from __future__ import annotations

import os
import time
from typing import Any

from lib.destroy import destroy_instance
from lib.launch_instance import launch_one
from lib.sku_offers import validate_offer
from lib.vast import normalize_vast_list, vastai

TIMEOUT = int(os.environ.get("WAIT_TIMEOUT_SEC", "1500"))
POLL = 15
FAIL_STATUSES = frozenset({"exited", "unknown", "offline", "stopped"})
PROVISIONING_LABEL = "provisioning"


def status_display(status: str | None) -> str:
    if status is None:
        return PROVISIONING_LABEL
    return status


def parse_instance_status(inst: dict[str, Any]) -> str | None:
    actual = inst.get("actual_status")
    if actual is not None:
        return str(actual)
    status = inst.get("status")
    if status is not None:
        return str(status)
    return None


def fetch_instance(instance_id: int) -> dict[str, Any]:
    raw = vastai("show", "instance", str(instance_id))
    rows = normalize_vast_list(raw)
    return rows[0] if rows else {}


def instance_status(instance_id: int) -> str | None:
    return parse_instance_status(fetch_instance(instance_id))


def _format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes}m"


def _truncate_msg(msg: str, max_len: int = 160) -> str:
    collapsed = " ".join(msg.split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 3] + "..."


def _instance_image(inst: dict[str, Any]) -> str | None:
    for key in ("image", "image_uuid", "image_args"):
        value = inst.get(key)
        if value:
            return str(value)
    return None


def host_snapshot_key(inst: dict[str, Any]) -> tuple[Any, ...]:
    return (
        inst.get("gpu_name"),
        inst.get("geolocation"),
        inst.get("reliability"),
        inst.get("inet_down"),
        _instance_image(inst),
    )


def format_host_snapshot(inst: dict[str, Any]) -> str:
    parts: list[str] = []
    gpu = inst.get("gpu_name")
    if gpu:
        parts.append(str(gpu))
    geo = inst.get("geolocation")
    if geo:
        parts.append(str(geo))
    rel = inst.get("reliability")
    if rel is not None:
        parts.append(f"reliability={rel}")
    inet = inst.get("inet_down")
    if inet is not None:
        parts.append(f"inet_down={inet}Mbps")
    image = _instance_image(inst)
    if image:
        parts.append(f"image={image}")
    if not parts:
        return ""
    return "  host: " + "  ".join(parts)


def format_wait_line(
    instance_id: int,
    inst: dict[str, Any],
    deadline: float,
    now: float | None = None,
) -> str:
    now = now or time.time()
    status = parse_instance_status(inst)
    parts = [f"instance {instance_id}:", status_display(status)]

    start = inst.get("start_date")
    if start is not None:
        try:
            elapsed = now - float(start)
            parts.append(_format_duration(elapsed))
        except (TypeError, ValueError):
            pass

    remaining = deadline - now
    if remaining > 0:
        parts.append(f"{_format_duration(remaining)} left")

    intended = inst.get("intended_status")
    if intended and intended != status and status is not None:
        parts.append(f"intended={intended}")

    cur_state = inst.get("cur_state")
    if cur_state and cur_state != status:
        parts.append(f"cur_state={cur_state}")

    status_msg = inst.get("status_msg")
    if status_msg:
        parts.append(f'msg="{_truncate_msg(str(status_msg))}"')

    return "  " + "  ".join(parts)


def wait_instance(instance_id: int) -> str:
    deadline = time.time() + TIMEOUT
    last_host_key: tuple[Any, ...] | None = None
    while time.time() < deadline:
        now = time.time()
        inst = fetch_instance(instance_id)
        status = parse_instance_status(inst)

        host_key = host_snapshot_key(inst)
        if host_key != last_host_key:
            snapshot = format_host_snapshot(inst)
            if snapshot:
                print(snapshot)
            last_host_key = host_key

        print(format_wait_line(instance_id, inst, deadline, now))

        if status == "running":
            return "running"
        if status is not None and status in FAIL_STATUSES:
            return status
        time.sleep(POLL)
    return "timeout"


def candidate_by_id(offers: dict[str, Any], sku_id: str, offer_id: Any) -> dict[str, Any] | None:
    block = offers.get("skus", {}).get(sku_id, {})
    for cand in block.get("candidates") or []:
        if cand.get("id") == offer_id:
            return cand
    return None


def retry_backups(
    sku_id: str,
    rec: dict[str, Any],
    offers: dict[str, Any],
    sku_meta: dict[str, Any],
) -> dict[str, Any] | None:
    backups = list(rec.get("backup_offer_ids") or [])
    last_fail_status = rec.get("actual_status")
    last_fail_iid = rec.get("instance_id")
    for offer_id in backups:
        offer = candidate_by_id(offers, sku_id, offer_id)
        if not offer:
            print(f"  backup offer {offer_id} not found in offers.yaml")
            continue
        err = validate_offer(sku_id, offer, sku_meta)
        if err:
            print(f"  skip backup {offer_id}: {err}")
            continue
        print(f"  Retrying {sku_id} with backup offer {offer_id}")
        new_rec = launch_one(sku_id, offer, sku_meta)
        if not new_rec:
            continue
        result = wait_instance(int(new_rec["instance_id"]))
        new_rec["actual_status"] = result
        last_fail_status = result
        last_fail_iid = new_rec["instance_id"]
        if result == "running":
            new_rec["backup_offer_ids"] = [oid for oid in backups if oid != offer_id]
            return new_rec
        print(f"  Backup instance {new_rec['instance_id']} failed ({result}) — destroying")
        destroy_instance(new_rec, sku_id)
    rec["instance_id"] = last_fail_iid
    rec["actual_status"] = last_fail_status
    if last_fail_status != "running":
        rec["error"] = f"never reached running ({last_fail_status})"
    return None


def retry_ssh_backups(
    sku_id: str,
    rec: dict[str, Any],
    offers: dict[str, Any],
    sku_meta: dict[str, Any],
) -> dict[str, Any] | None:
    """Destroy path already ran; launch backup offers until SSH auth succeeds."""
    from lib.ssh_preflight import attach_instance_ssh
    from lib.ssh_remote import SshNotReadyError, wait_for_ssh

    backups = list(rec.get("backup_offer_ids") or [])
    last_fail_iid = rec.get("instance_id")
    for offer_id in backups:
        offer = candidate_by_id(offers, sku_id, offer_id)
        if not offer:
            print(f"  backup offer {offer_id} not found in offers.yaml")
            continue
        err = validate_offer(sku_id, offer, sku_meta)
        if err:
            print(f"  skip backup {offer_id}: {err}")
            continue
        print(f"  Retrying {sku_id} with backup offer {offer_id} (SSH auth failed)")
        new_rec = launch_one(sku_id, offer, sku_meta)
        if not new_rec:
            continue
        result = wait_instance(int(new_rec["instance_id"]))
        new_rec["actual_status"] = result
        last_fail_iid = new_rec["instance_id"]
        if result != "running":
            print(f"  Backup instance {new_rec['instance_id']} failed ({result}) — destroying")
            destroy_instance(new_rec, sku_id)
            continue
        iid = int(new_rec["instance_id"])
        try:
            attach_instance_ssh(iid)
            wait_for_ssh(iid)
        except SshNotReadyError:
            print(f"  Backup instance {iid} SSH auth failed — destroying")
            destroy_instance(new_rec, sku_id)
            continue
        new_rec["backup_offer_ids"] = [oid for oid in backups if oid != offer_id]
        return new_rec
    rec["instance_id"] = last_fail_iid
    rec["error"] = "ssh auth failed (all candidates)"
    return None


def wait_until_running(
    sku_id: str,
    rec: dict[str, Any],
    offers: dict[str, Any],
    sku_meta: dict[str, Any],
) -> dict[str, Any] | None:
    """Wait for instance to run; on failure destroy and try backup offers."""
    iid = rec.get("instance_id")
    if not iid:
        return None

    print(f"Waiting {sku_id} instance {iid}...")
    result = wait_instance(int(iid))
    rec["actual_status"] = result
    if result == "running":
        return rec

    print(f"  Destroying failed instance {iid}")
    destroy_instance(rec, sku_id)

    rec["error"] = f"never reached running ({result})"
    replacement = retry_backups(sku_id, rec, offers, sku_meta)
    if replacement:
        print(f"  {sku_id} recovered on backup offer {replacement.get('offer_id')}")
    return replacement
