#!/usr/bin/env python3
"""Launch one Vast offer, verify SSH auth, destroy — minimal billing smoke test."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.destroy import destroy_instance  # noqa: E402
from lib.launch_instance import resolve_image  # noqa: E402
from lib.push_and_run import push_harness  # noqa: E402
from lib.sku_offers import validate_offer  # noqa: E402
from lib.ssh_preflight import attach_instance_ssh, ensure_ssh_ready  # noqa: E402
from lib.ssh_remote import log_ssh_endpoint, ssh_probe, wait_for_ssh  # noqa: E402
from lib.transport import use_onstart_transport  # noqa: E402
from lib.vast import load_dotenv, read_yaml, vastai  # noqa: E402
from lib.wait_running import wait_instance  # noqa: E402

OFFERS_PATH = ROOT / "config" / "offers.yaml"
MATRIX_PATH = ROOT / "config" / "matrix.yaml"
DEFAULT_DISK_GB = 40
DEFAULT_LABEL = "ssh-smoke"


def load_offer_by_id(offer_id: int) -> tuple[str, dict[str, Any], dict[str, Any]]:
    if not OFFERS_PATH.is_file():
        raise SystemExit(f"Missing {OFFERS_PATH} — run 01_search_offers.py first")
    offers = read_yaml(OFFERS_PATH)
    matrix = read_yaml(MATRIX_PATH) if MATRIX_PATH.is_file() else {}
    matrix_skus = matrix.get("skus", {})
    for sku_id, block in offers.get("skus", {}).items():
        sku_meta = block.get("sku_meta") or matrix_skus.get(sku_id, {})
        for cand in block.get("candidates") or []:
            if int(cand.get("id")) == offer_id:
                return sku_id, cand, sku_meta
    raise SystemExit(f"Offer {offer_id} not found in {OFFERS_PATH}")


def load_offer_for_sku(sku_id: str, candidate_index: int) -> tuple[int, dict[str, Any], dict[str, Any]]:
    if not OFFERS_PATH.is_file():
        raise SystemExit(f"Missing {OFFERS_PATH} — run 01_search_offers.py first")
    offers = read_yaml(OFFERS_PATH)
    matrix = read_yaml(MATRIX_PATH) if MATRIX_PATH.is_file() else {}
    block = offers.get("skus", {}).get(sku_id)
    if not block:
        raise SystemExit(f"SKU {sku_id} not found in {OFFERS_PATH}")
    candidates = block.get("candidates") or []
    if not candidates:
        raise SystemExit(f"No candidates for {sku_id} in {OFFERS_PATH}")
    if candidate_index < 0 or candidate_index >= len(candidates):
        raise SystemExit(
            f"candidate-index {candidate_index} out of range "
            f"(0..{len(candidates) - 1}) for {sku_id}"
        )
    sku_meta = block.get("sku_meta") or matrix.get("skus", {}).get(sku_id, {})
    cand = candidates[candidate_index]
    offer_id = cand.get("id")
    if not offer_id:
        raise SystemExit(f"Candidate {candidate_index} for {sku_id} has no id")
    return int(offer_id), cand, sku_meta


def format_offer_summary(offer_id: int, offer: dict[str, Any]) -> str:
    parts = [f"offer={offer_id}"]
    gpu = offer.get("gpu_name")
    if gpu:
        parts.append(str(gpu))
    geo = offer.get("geolocation")
    if geo:
        parts.append(str(geo))
    dph = offer.get("dph_total")
    if dph is not None:
        parts.append(f"${float(dph):.2f}/hr")
    rel = offer.get("reliability")
    if rel is not None:
        parts.append(f"reliability={rel}")
    return "  ".join(parts)


def launch_smoke(
    sku_id: str,
    offer_id: int,
    offer: dict[str, Any],
    sku_meta: dict[str, Any],
    *,
    label: str,
    disk_gb: int,
) -> dict[str, Any]:
    err = validate_offer(sku_id, offer, sku_meta)
    if err:
        raise SystemExit(f"Offer {offer_id} invalid for {sku_id}: {err}")

    image = resolve_image(offer, sku_meta)
    print(f"Launching SSH smoke {format_offer_summary(offer_id, offer)}")
    print(f"  image={image} disk={disk_gb}GB label={label}")

    result = vastai(
        "create",
        "instance",
        str(offer_id),
        "--image",
        image,
        "--disk",
        str(disk_gb),
        "--ssh",
        "--direct",
        "--label",
        label,
        "--cancel-unavail",
        check=False,
    )
    if not isinstance(result, dict) or not result.get("success"):
        msg = result.get("msg") or result.get("message") if isinstance(result, dict) else result
        raise SystemExit(f"Launch failed: {msg or result}")

    iid = result.get("new_contract") or result.get("id")
    print(f"  -> instance id {iid}")
    return {
        "sku_id": sku_id,
        "instance_id": iid,
        "offer_id": offer_id,
        "label": label,
        "image": image,
        "dph_total": offer.get("dph_total"),
        "gpu_name": offer.get("gpu_name"),
    }


def run_smoke(rec: dict[str, Any], sku_id: str, *, push_harness_flag: bool = False) -> int:
    iid = int(rec["instance_id"])
    print(f"Waiting instance {iid}...")
    status = wait_instance(iid)
    if status != "running":
        print(f"Instance {iid} never reached running ({status})")
        return 1

    attach_instance_ssh(iid)
    wait_for_ssh(iid)
    log_ssh_endpoint(iid)

    ok, out, err = ssh_probe(iid, "echo ok && whoami", timeout=30)
    if not ok:
        print(f"SSH probe failed: {err}")
        return 1
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    if not lines or lines[0] != "ok":
        print(f"SSH probe unexpected output: {out!r}")
        return 1
    user = lines[1] if len(lines) > 1 else "?"
    print(f"SSH smoke test OK — instance {iid} user={user}")

    if push_harness_flag:
        push_harness(iid)
        print(f"Harness push verified on instance {iid}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Launch one Vast offer, verify SSH, destroy (minimal billing)",
    )
    parser.add_argument(
        "--offer",
        type=int,
        metavar="ID",
        help="Vast offer id from config/offers.yaml",
    )
    parser.add_argument(
        "--sku",
        metavar="SKU",
        help="SKU id — test candidates[candidate-index] from offers.yaml",
    )
    parser.add_argument(
        "--candidate-index",
        type=int,
        default=0,
        help="Which candidate row to use with --sku (default: 0 = cheapest/first)",
    )
    parser.add_argument(
        "--disk",
        type=int,
        default=DEFAULT_DISK_GB,
        metavar="GB",
        help=f"Instance disk size (default: {DEFAULT_DISK_GB})",
    )
    parser.add_argument(
        "--label",
        default=DEFAULT_LABEL,
        help=f"Instance label (default: {DEFAULT_LABEL})",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="After SSH auth, push harness via tar|ssh and verify start_matrix.sh",
    )
    args = parser.parse_args()

    if args.offer is not None and args.sku:
        raise SystemExit("Use --offer or --sku, not both")
    if args.offer is None and not args.sku:
        raise SystemExit("Specify --offer ID or --sku SKU (run 01_search_offers.py first)")

    load_dotenv()
    ensure_ssh_ready()
    if use_onstart_transport():
        raise SystemExit(
            "SSH smoke test needs a personal API key and ~/.ssh/id_ed25519.pub "
            "registered at https://cloud.vast.ai/manage-keys/"
        )

    if args.offer is not None:
        sku_id, offer, sku_meta = load_offer_by_id(args.offer)
        offer_id = args.offer
    else:
        offer_id, offer, sku_meta = load_offer_for_sku(args.sku, args.candidate_index)
        sku_id = args.sku

    print(f"== SSH smoke test ({sku_id}) ==")
    print(f"  {format_offer_summary(offer_id, offer)}")

    rec: dict[str, Any] = {}
    exit_code = 1
    try:
        rec = launch_smoke(
            sku_id,
            offer_id,
            offer,
            sku_meta,
            label=args.label,
            disk_gb=args.disk,
        )
        exit_code = run_smoke(rec, sku_id, push_harness_flag=args.push)
    except KeyboardInterrupt:
        print("\nInterrupted — destroying instance")
        exit_code = 130
    finally:
        if rec.get("instance_id"):
            destroy_instance(rec, sku_id)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
