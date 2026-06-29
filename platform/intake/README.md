# Intake service (capture layer)

One endpoint, many sources. Decouples capture from processing.

## Accepts
- Meeting transcript webhooks (Recall.ai; optionally tl;dv).
- Pulled Otter transcripts (via Otter MCP — already connected).
- Voice-note audio uploads → streaming STT (shared with the voice agent).

## Does
1. Normalize any payload into the standard transcript object (`transcript.schema.md`).
2. Write it to `/vault/Inbox/transcripts/`.
3. Signal the agent to process: extract action items, draft emails (Gmail MCP),
   propose calendar events (Calendar MCP), file the note. Sends require approval.

> Stub — implemented in Phase 4.
