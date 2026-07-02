#!/bin/sh
# Upsert a secret into the tenant .env without it ever appearing in a terminal,
# chat log, or shell history. Run ON the box:
#   ssh -t <box> '~/personal-ai-os/scripts/add-secret.sh TWENTY_API_KEY'
# Prompts silently, replaces or appends the variable, then restarts the agent
# so the new key is live.
set -eu

VAR="${1:?usage: add-secret.sh VAR_NAME}"
ENV_FILE="$(dirname "$0")/../.env"

printf 'Paste value for %s (input hidden): ' "$VAR"
stty -echo; read -r VALUE; stty echo; printf '\n'
[ -n "$VALUE" ] || { echo "empty value, aborting"; exit 1; }

if grep -q "^${VAR}=" "$ENV_FILE"; then
  # sed -i portability: write a temp file instead
  tmp="$(mktemp)"
  grep -v "^${VAR}=" "$ENV_FILE" > "$tmp"
  printf '%s=%s\n' "$VAR" "$VALUE" >> "$tmp"
  cat "$tmp" > "$ENV_FILE" && rm -f "$tmp"
  echo "replaced ${VAR} in .env"
else
  printf '%s=%s\n' "$VAR" "$VALUE" >> "$ENV_FILE"
  echo "added ${VAR} to .env"
fi

cd "$(dirname "$0")/.."
docker compose --env-file .env -f platform/docker-compose.yml up -d agent
echo "agent restarted — ${VAR} is live"
