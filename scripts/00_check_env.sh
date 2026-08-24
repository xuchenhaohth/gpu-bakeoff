#!/usr/bin/env bash
# Pre-flight checks before any Vast billing.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== gpu-bakeoff environment check =="

fail=0
warn() { echo "WARN: $*"; }
die() { echo "ERROR: $*"; fail=1; }

# .env
if [[ ! -f .env ]]; then
  die "Missing .env — copy from .env.example and set VAST_API_KEY, HF_TOKEN"
else
  echo "OK  .env exists"
  # shellcheck disable=SC1091
  set -a && source .env && set +a
fi

# vastai CLI
if command -v vastai >/dev/null 2>&1; then
  echo "OK  vastai $(vastai --version 2>/dev/null || true)"
else
  die "vastai CLI not found — curl -fsSL https://vast.ai/install.sh | bash"
fi

# Python + PyYAML
if command -v python3 >/dev/null 2>&1; then
  echo "OK  python3 $(python3 --version)"
  python3 -c "import yaml" 2>/dev/null || die "pip install pyyaml"
else
  die "python3 not found"
fi

# SSH key
for k in "$HOME/.ssh/id_ed25519.pub" "$HOME/.ssh/id_rsa.pub"; do
  if [[ -f "$k" ]]; then
    echo "OK  SSH public key: $k"
    break
  fi
done
if [[ ! -f "${k:-}" ]]; then
  warn "No SSH public key found — run: ssh-keygen -t ed25519 && vastai create ssh-key ~/.ssh/id_ed25519.pub"
fi

# API key auth
if [[ -z "${VAST_API_KEY:-}" ]]; then
  die "VAST_API_KEY empty in .env"
else
  if vastai show user --raw 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK  Vast user:', d.get('email','?'), 'credit:', d.get('credit','?'))" 2>/dev/null; then
    :
  else
    die "vastai auth failed — check VAST_API_KEY"
  fi
fi

if [[ -z "${HF_TOKEN:-}" ]]; then
  warn "HF_TOKEN empty — gated models will fail prefetch"
else
  echo "OK  HF_TOKEN set (${#HF_TOKEN} chars)"
fi

MAX="${MAX_USD:-180}"
MIN="${MIN_CREDIT_USD:-50}"
echo "OK  spend cap MAX_USD=$MAX MIN_CREDIT_USD=$MIN"

mkdir -p results results/artifacts config
echo "OK  results/ and config/ ready"

if [[ "$fail" -ne 0 ]]; then
  echo "== FAILED =="
  exit 1
fi
echo "== Ready for 01_search_offers.py =="
