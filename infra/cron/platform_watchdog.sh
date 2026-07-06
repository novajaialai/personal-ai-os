#!/usr/bin/env bash
# platform_watchdog.sh — zero-token watchdog for the aios VPS.
# Hermes cron runs this with --no-agent: stdout is delivered verbatim,
# EMPTY stdout = silent (no message, no LLM call). Only speak on problems.
#
# Register (on the VPS):
#   hermes cron create "every 30m" --name platform-watchdog \
#     --script platform_watchdog.sh --no-agent --deliver local
# Script must live at ~/.hermes/scripts/platform_watchdog.sh

PROBLEMS=()

# 1. Expected docker containers running
EXPECTED="platform-agent-1 platform-caddy-1 platform-db-1 platform-intake-1 \
platform-metabase-1 platform-n8n-1 platform-nango-1 platform-nextcloud-1 \
platform-twenty-db-1 platform-twenty-redis-1 platform-twenty-server-1 platform-twenty-worker-1"
RUNNING=$(docker ps --format '{{.Names}}' 2>/dev/null)
for c in $EXPECTED; do
  grep -qx "$c" <<<"$RUNNING" || PROBLEMS+=("container DOWN: $c")
done

# 2. System services
for svc in cloudflared; do
  systemctl is-active --quiet "$svc" || PROBLEMS+=("service DOWN: $svc")
done
for usvc in hermes-gateway cognee; do
  systemctl --user is-active --quiet "$usvc" || PROBLEMS+=("user service DOWN: $usvc")
done

# 3. Disk
USE=$(df --output=pcent / | tail -1 | tr -dc '0-9')
[ "$USE" -ge 85 ] && PROBLEMS+=("disk at ${USE}% on /")

# 4. Front door: Access must answer (302 to login) on the tunnel
CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-redirs 0 --max-time 15 https://aios.jacobdart.com/ 2>/dev/null)
[ "$CODE" = "302" ] || [ "$CODE" = "200" ] || PROBLEMS+=("tunnel front door bad: aios.jacobdart.com returned '$CODE'")

# 5. Local app answering behind Caddy
LCODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8080/ 2>/dev/null)
[ "$LCODE" = "200" ] || [ "$LCODE" = "302" ] || PROBLEMS+=("caddy/agent :8080 returned '$LCODE'")

if [ ${#PROBLEMS[@]} -gt 0 ]; then
  echo "AIOS WATCHDOG — $(hostname) — ${#PROBLEMS[@]} problem(s):"
  printf ' - %s\n' "${PROBLEMS[@]}"
fi
