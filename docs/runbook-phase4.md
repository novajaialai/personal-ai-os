# Personal AI OS — Phase 4 Runbook (v1)

**Goal:** give the agent hands. Wire connectors (MCP-native → self-hosted Nango), build the
**capture layer** (intake + normalizer), and prove the **transcript-to-action loop** — a meeting
becomes a drafted confirmation email and a proposed calendar event, waiting for your approval.
This is the core of the executive assistant and the highest-value demo in the whole build.

**Prerequisite:** Phase 3 complete — agent reachable over the tailnet, SQLite sessions, WebDAV vault
writes proven.

---

## Design notes

- **Auth order is a hard rule:** MCP-native first → self-hosted Nango → hand-roll. No Composio.
- **Nothing sends unattended.** The agent *drafts* and *proposes*; a human approves. Enforce this
  with an approvals queue, not good intentions.
- **Capture is decoupled from processing.** One intake endpoint; sources are swappable; everything
  normalizes to the same transcript object and lands in the vault.
- **Personas are the same agent** in different namespaces (system prompt + skill pack), not new
  services.

---

## 4.1 Connector auth

**MCP-native (Gmail, Google Calendar, Otter):** connect each via its OAuth 2.1 + PKCE flow — one
browser login; tokens persist to the encrypted store. Register them as tools the agent can call.

**Self-hosted Nango (REST-only apps):** the `nango` service is already in compose. Configure it and
do the one-time OAuth per provider:
```bash
# on the box
docker compose -f platform/docker-compose.yml up -d nango
# in the Nango dashboard (tailnet-only): add provider configs, run the OAuth connect flow once.
# The agent then calls providers through Nango's proxy; tokens live in Nango's encrypted Postgres.
```
Token storage: MCP tokens → SOPS/encrypted store; Nango tokens → Nango's own encrypted DB. Both on
your box. Nango's credential DB must be in the restic include list (4.8).

## 4.2 Agent tools + the approvals gate
Expose tools to the agent: `gmail.draft`, `calendar.propose`, `vault.note_write` (from Phase 3),
`nango.call`. **Send/create actions never fire directly** — they write to an approvals queue:
```
/vault/Inbox/approvals/<id>.md   # one file per proposed action
---
type: email            # email | calendar_event
status: pending        # pending | approved | sent | rejected
to: dana@acme.com
subject: Confirming today's scope
body: >
---
```
A human (you, via Obsidian or a device UI) flips `status: approved`; a small watcher then executes
the send via the connector and updates `status: sent`. Reject = do nothing. This is guardrail #6.

## 4.3 Intake service (capture layer)
Implement `platform/intake`:
- **Endpoint** `POST /intake` behind Caddy (tailnet-only), plus a pull path for Otter (MCP).
- **Normalizer** → the transcript object in `platform/intake/transcript.schema.md`.
- **Write** to `/vault/Inbox/transcripts/` via WebDAV (single-coordinator rule — no raw disk).
- On new transcript, signal the agent to process it.

## 4.4 Prove the loop on Otter MCP first (already connected)
Lowest-lift end-to-end proof, no new infra:
1. Pull a recent Otter meeting transcript via the Otter MCP.
2. Normalize → write to `/vault/Inbox/transcripts/`.
3. Agent processes: extracts action items → drafts a confirmation email (`gmail.draft`) and proposes
   a calendar event (`calendar.propose`) → both land in `/vault/Inbox/approvals/`.
4. You approve one; the watcher sends it; status flips to `sent`.

**This is the acceptance demo for the phase.** A real meeting produced a real drafted action you
approved, end to end, on your own box.

## 4.5 Consolidate on Recall.ai
Once the loop works, swap the source without changing anything downstream:
```bash
# Register a Recall.ai bot / real-time webhook pointed at:
#   https://aios-jake.<tailnet>.ts.net/intake
# Recall pushes recording + transcript → same normalizer → same vault path → same agent loop.
```
Note Recall's 7-day free storage — the intake must pull/persist transcripts promptly (they're your
system of record, not Recall's).

## 4.6 Personas (modes)
Route by session namespace to a system prompt + skill pack:
```
second_brain | ea | tutor | trainer | coach
```
Keep prompts in `platform/agent/personas/`. Phase 4 wires the EA (mail/calendar/tasks) and
second-brain (capture/recall) fully; tutor/trainer/coach get baseline prompts now, spaced-repetition
and depth land later.

## 4.7 Security
- Connector tokens encrypted, on-box (SOPS store or Nango DB). Never in the vault, never in git.
- Approvals gate enforced for every external action.
- Every agent action appended to an audit log in the vault (`/vault/Logs/agent-YYYY-MM.md`).
- Intake + Nango dashboard are tailnet-only; re-run the public-IP `nc` refuse test after adding services.

## 4.8 Backups
```bash
# Nango's credential DB is now critical state — confirm it's captured
restic backup /srv/aios --tag aios
restic snapshots
```

---

## Acceptance criteria (Phase 4 done)
- [ ] MCP-native connectors (Gmail, Calendar, Otter) authorized; tokens on-box, encrypted.
- [ ] Nango up for any REST-only provider; tokens in its encrypted DB; DB in restic.
- [ ] Intake writes a normalized transcript to the vault via WebDAV.
- [ ] **Otter → transcript → drafted email + proposed event → approvals → you approve → sent.**
- [ ] No external action ever fires without an approval flip.
- [ ] Recall.ai path produces the same normalized transcript as Otter.
- [ ] Persona routing works; EA + second-brain fully wired.
- [ ] Public-IP `nc` refuse test still passes after new services.

## Next (Phase 5 preview)
Voice: push-to-talk MVP on phone/tablet reusing the STT pipeline, wired to the same agent + session
store so voice and text share memory. Then iterate toward realtime if it earns its keep.
