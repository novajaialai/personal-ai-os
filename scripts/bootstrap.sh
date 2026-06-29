#!/usr/bin/env bash
# Bring up the platform on a freshly provisioned, hardened VPS.
# Run as the 'aios' user on the box (over Tailscale SSH).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> 1. Secrets"
if [ ! -f .env ]; then
  cp templates/.env.example .env
  # Generate strong random secrets where blank
  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -hex 24)|" .env
  sed -i "s|^NANGO_ENCRYPTION_KEY=.*|NANGO_ENCRYPTION_KEY=$(openssl rand -base64 32)|" .env
  echo "    .env created — add your BYO API keys (ANTHROPIC_API_KEY, etc.) before continuing."
  echo "    Then encrypt it: sops --encrypt --age <key> .env > secrets/.env.age"
  exit 0
fi

echo "==> 2. Vault (git-managed)"
VAULT_PATH=$(grep '^VAULT_PATH=' .env | cut -d= -f2)
mkdir -p "$VAULT_PATH/Inbox/transcripts"
git -C "$VAULT_PATH" init -q 2>/dev/null || true

echo "==> 3. Platform up"
docker compose -f platform/docker-compose.yml up -d

echo "==> Done. Next: ./scripts/customize.sh to personalize this tenant."
