#!/usr/bin/env bash
# Proactive daily check-in: asks the agent to review the vault on its own
# and surface anything that needs attention, without Jake asking first.
# Deployed as a systemd timer (see infra/systemd/aios-daily-briefing.*).
set -euo pipefail

AGENT_URL="${AGENT_URL:-http://127.0.0.1:8080}"
TODAY="$(date -u +%F)"

# The agent has no reliable clock of its own — inject the real date rather
# than letting it guess (it previously hallucinated 2025-07-14 on a
# 2026-07-01 run).
python3 -c '
import json, sys
msg = (
    "Proactive daily check-in for " + sys.argv[1] + " — no one asked, this "
    "runs on a schedule. Review Inbox/leads/, Inbox/transcripts/, and "
    "Inbox/approvals/ for anything that has been sitting unactioned for more "
    "than a day, and Inbox/action-items.md for anything overdue. Write a "
    "short digest to exactly this path: Inbox/Digests/" + sys.argv[1] + ".md "
    "— what is new, what is pending, what needs a decision. If nothing is "
    "pending, say so briefly, do not pad it out. Do not send or schedule "
    "anything, this is a summary only."
)
print(json.dumps({"session_id": "daily-briefing", "message": msg}))
' "$TODAY" | curl -sf -X POST "$AGENT_URL/chat" -H "Content-Type: application/json" -d @-
