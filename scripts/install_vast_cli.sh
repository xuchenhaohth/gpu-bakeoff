#!/usr/bin/env bash
# Install Vast.ai CLI on macOS/Linux
set -euo pipefail
if command -v vastai >/dev/null 2>&1; then
  echo "vastai already installed: $(vastai --version 2>/dev/null || true)"
  exit 0
fi
curl -fsSL https://vast.ai/install.sh | bash
echo "Installed. Next: vastai set api-key <KEY> && vastai create ssh-key \"\$(cat ~/.ssh/id_ed25519.pub)\""
