#!/usr/bin/env bash
# ops_brief_data.sh — pre-run data gatherer for the daily ops brief.
# Hermes cron runs this WITHOUT --no-agent: stdout is injected into the
# agent's prompt, so the model formats data the script fetched for free
# instead of burning tool calls discovering it.
#
# Register (on the VPS):
#   hermes cron create "0 13 * * *" --name daily-ops-brief \
#     --script ops_brief_data.sh --deliver local \
#     "Format this into a tight morning ops brief for Jake (owner of this VPS). \
#      Lead with anything broken or unusual, then one line each: platform health, \
#      disk, kanban, recent vault activity. No fluff. If everything is nominal, \
#      say so in two sentences max."

echo "=== date ==="
date -u +"%Y-%m-%d %H:%M UTC"

echo "=== containers (expect 12 Up) ==="
docker ps --format '{{.Names}}\t{{.Status}}' | sort

echo "=== services ==="
for s in cloudflared; do printf '%s: %s\n' "$s" "$(systemctl is-active "$s")"; done
for s in hermes-gateway cognee; do printf '%s: %s\n' "$s" "$(systemctl --user is-active "$s")"; done

echo "=== disk ==="
df -h / | tail -1

echo "=== front door ==="
for h in agentos aios crm metabase n8n; do
  printf '%s.jacobdart.com: %s\n' "$h" \
    "$(curl -s -o /dev/null -w '%{http_code}' --max-redirs 0 --max-time 10 https://$h.jacobdart.com/)"
done

echo "=== kanban ==="
if [ -f "$HOME/.hermes/kanban.db" ]; then
  python3 - <<'PY' 2>/dev/null || echo "kanban unreadable"
import sqlite3, os
db = sqlite3.connect(os.path.expanduser("~/.hermes/kanban.db"))
tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
t = next((x for x in ("cards", "tasks", "kanban_cards") if x in tables), None)
if t:
    for status, n in db.execute(f"SELECT status, COUNT(*) FROM {t} GROUP BY status"):
        print(f"{status}: {n}")
else:
    print("no card table (tables: %s)" % ", ".join(tables) if tables else "empty board")
PY
fi

echo "=== vault activity (last 24h) ==="
find /srv/aios/vault -type f -mtime -1 -not -path '*/.git/*' 2>/dev/null | head -15
