#!/usr/bin/env bash
# Proactive daily check-in: reviews the vault on a schedule, without Jake
# asking first. Deployed as a systemd timer (infra/systemd/aios-daily-briefing.*).
#
# Deterministic pre-check first: if there's genuinely nothing new to review,
# skip the LLM call entirely and write the digest directly. Burning Claude
# subscription quota to report "nothing pending" is exactly the waste a
# quota-first routing policy (see novajaialai/switchboard) exists to avoid —
# the cheapest, most correct route for a trivial check is no model call at
# all, not just a cheaper model.
set -euo pipefail

VAULT="${VAULT_PATH:-/srv/aios/vault}"
AGENT_URL="${AGENT_URL:-http://127.0.0.1:8080}"
TODAY="$(date -u +%F)"
DIGEST="$VAULT/Inbox/Digests/$TODAY.md"

count_md() { find "$1" -name '*.md' 2>/dev/null | wc -l; }

leads=$(count_md "$VAULT/Inbox/leads")
transcripts=$(count_md "$VAULT/Inbox/transcripts")
approvals=$(count_md "$VAULT/Inbox/approvals")
open_items=0
if [ -f "$VAULT/Inbox/action-items.md" ]; then
  open_items=$(grep -c '^\- \[ \]' "$VAULT/Inbox/action-items.md" || true)
fi

mkdir -p "$VAULT/Inbox/Digests"

if [ "$leads" -eq 0 ] && [ "$transcripts" -eq 0 ] && [ "$approvals" -eq 0 ] && [ "$open_items" -eq 0 ]; then
  # Nothing pending — deterministic, zero-cost path. No LLM call.
  cat > "$DIGEST" <<EOF
# Daily digest — $TODAY

Nothing pending. No leads, transcripts, or approvals waiting; no open
action items. (Written by the deterministic pre-check — no model call
needed for an empty inbox.)
EOF
  exit 0
fi

# There's real content — this needs actual judgment, route to the agent.
python3 -c '
import json, sys
msg = (
    "Proactive daily check-in for " + sys.argv[1] + " — no one asked, this "
    "runs on a schedule. Review Inbox/leads/, Inbox/transcripts/, and "
    "Inbox/approvals/ for anything that has been sitting unactioned for more "
    "than a day, and Inbox/action-items.md for anything overdue. Write a "
    "short digest to exactly this path: Inbox/Digests/" + sys.argv[1] + ".md "
    "— what is new, what is pending, what needs a decision. Do not send or "
    "schedule anything, this is a summary only."
)
print(json.dumps({"session_id": "daily-briefing", "message": msg}))
' "$TODAY" | curl -sf -X POST "$AGENT_URL/chat" -H "Content-Type: application/json" -d @-
