#!/usr/bin/env bash
# Load HF_TOKEN for remote harness (SSH sessions lack Docker -e).
BAKEOFF_ROOT="${BAKEOFF_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
HF_ENV_FILE="$BAKEOFF_ROOT/.env.hf"

if [[ -f "$HF_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$HF_ENV_FILE"
  set +a
elif [[ -r /proc/1/environ ]]; then
  while IFS= read -r -d '' var; do
    case "$var" in
      HF_TOKEN=*|HUGGING_FACE_HUB_TOKEN=*|HF_RESULTS_REPO=*)
        export "$var"
        ;;
    esac
  done < /proc/1/environ
fi
export HUGGING_FACE_HUB_TOKEN="${HUGGING_FACE_HUB_TOKEN:-${HF_TOKEN:-}}"
