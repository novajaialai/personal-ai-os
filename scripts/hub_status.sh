#!/usr/bin/env bash
# hub_status.sh — writes platform/hub/status.json for the Machine Room page.
# Installed by the hub deploy; cron: */5 * * * *
set -uo pipefail
OUT="$HOME/personal-ai-os/platform/hub/status.json"

up() {  # container running?
  docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null | grep -q true && echo true || echo false
}
port_ok() {  # host process answering?
  curl -so /dev/null --max-time 4 "http://127.0.0.1:$1" && echo true || echo false
}

containers_total=$(docker ps -a --format '{{.Names}}' | grep -c '^platform-')
containers_up=$(docker ps --format '{{.Names}}' | grep -c '^platform-')
load1=$(cut -d' ' -f1 /proc/loadavg)
cpus=$(nproc)
mem_used_pct=$(free | awk '/Mem:/ {printf "%.0f", $3/$2*100}')
disk_used_pct=$(df / --output=pcent | tail -1 | tr -dc '0-9')
uptime_h=$(uptime -p | sed 's/^up //; s/ weeks\?/w/; s/ days\?/d/; s/ hours\?/h/; s/ minutes\?/m/; s/,//g')
aeo_last=$(ls -t "$HOME/projects/aeo-engine/out/"*/*.html 2>/dev/null | head -1 | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' || echo "")

cat > "$OUT" <<JSON
{
  "generated": "$(date -u +%FT%TZ)",
  "containers_up": $containers_up,
  "containers_total": $containers_total,
  "load1": $load1,
  "cpus": $cpus,
  "mem_used_pct": $mem_used_pct,
  "disk_used_pct": $disk_used_pct,
  "uptime": "$uptime_h",
  "aeo_last": "$aeo_last",
  "services": {
    "agent": $(up platform-agent-1),
    "agentos": $(port_ok 3737),
    "twenty": $(up platform-twenty-server-1),
    "metabase": $(up platform-metabase-1),
    "n8n": $(up platform-n8n-1),
    "nextcloud": $(up platform-nextcloud-1)
  }
}
JSON
