# Personal AI OS — Phase 3 Runbook

**Goal:** Deploy the headless Claude agent with SQLite session persistence. Prove "pick up where I left off" across two devices (text-first, no voice yet).

**After this phase:** Any device on the tailnet can open a conversation with the agent, and any other device can resume it with the same `session_id`.

---

## Prerequisites

- Phase 2 complete (Nextcloud running, tailscale serve active, VPS reachable)
- Your Anthropic API key (`sk-ant-...`)

---

## 3.1 — Add ANTHROPIC_API_KEY to the VPS

SSH in and append the key to `.env`:

```bash
ssh -i ~/.ssh/aios aios@178.156.169.121
echo "ANTHROPIC_API_KEY=sk-ant-YOUR_KEY_HERE" >> ~/personal-ai-os/.env
```

Verify it's there:
```bash
grep ANTHROPIC ~/personal-ai-os/.env
```

---

## 3.2 — Pull latest code and build the agent image

```bash
ssh -i ~/.ssh/aios aios@178.156.169.121 "
  cd ~/personal-ai-os && git pull
  docker compose -f platform/docker-compose.yml build agent
"
```

Build takes ~60s (downloads python:3.12-slim + deps).

---

## 3.3 — Start the agent + reload Caddy

```bash
ssh -i ~/.ssh/aios aios@178.156.169.121 "
  cd ~/personal-ai-os
  set -a; source .env; set +a
  docker compose -f platform/docker-compose.yml up -d agent
  docker compose -f platform/docker-compose.yml restart caddy
"
```

---

## 3.4 — Verify health

From VPS (localhost):
```bash
curl -s http://127.0.0.1:8080/health
# expect: {"status":"ok","model":"claude-sonnet-4-6"}
```

From Mac / any tailnet device:
```bash
curl -sk https://aios-jake-1.tail828365.ts.net/health
# expect: {"status":"ok","model":"claude-sonnet-4-6"}
```

---

## 3.5 — First conversation

Start a new session (no session_id = agent auto-creates one):
```bash
curl -sk -X POST https://aios-jake-1.tail828365.ts.net/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "My name is Jake. I build AI systems on Hetzner. What do you know about me?"}' \
  | python3 -m json.tool
```

Copy the returned `session_id`.

---

## 3.6 — Cross-device resume test (acceptance criterion)

From a **second device** (Mac, phone via Tailscale, etc.) — use the session_id from 3.5:
```bash
curl -sk -X POST https://aios-jake-1.tail828365.ts.net/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id": "PASTE_ID_HERE", "message": "What is my name and what am I building?"}' \
  | python3 -m json.tool
```

Claude must answer correctly. If it does: **Phase 3 complete.**

---

## 3.7 — List sessions

```bash
curl -sk https://aios-jake-1.tail828365.ts.net/sessions | python3 -m json.tool
```

---

## Troubleshooting

**Agent crashes on startup**
```bash
docker compose -f platform/docker-compose.yml logs agent
```
Most likely: `ANTHROPIC_API_KEY` missing from `.env`.

**Caddy returns 502 on /chat**
Agent is either not running or didn't start cleanly. Check logs.

**`session_id not found` on resume**
The SQLite database is in the `agent_state` Docker volume. If you re-created the container with `--volumes`, the DB was wiped. Don't pass `--volumes` unless resetting intentionally.

---

## What's next — Phase 4

- Intake service (Recall.ai / Otter webhooks → vault/Inbox/)
- MCP connectors (Gmail draft, Calendar propose via Nango)
- Personas (EA, tutor, coach — system-prompt packs)
- Onboarding interview skill (populate /vault/context/)
