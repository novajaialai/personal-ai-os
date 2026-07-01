# Personal AI OS — Phase 5 Runbook (v1)

**Goal:** talk to the agent. A **push-to-talk voice loop** from phone/tablet/Mac/Linux that reuses
the same agent and session store — so a thread you started by text continues by voice and vice
versa. Realtime is a later, gated spike; push-to-talk is the MVP that works in days.

**Prerequisite:** Phase 3 agent core running (endpoint + SQLite sessions). Phase 4 helpful (so voice
can trigger real actions through the approvals gate) but not required for the voice loop itself.

---

## Design notes

- **One brain, two input modes.** Voice hits the *same* agent + *same* `session_id`. Memory is
  shared; voice is just another transport.
- **Push-to-talk first.** No always-listening, no voice-activity-detection complexity. Hold a button,
  speak, release, get audio back. This removes 80% of the hard parts.
- **STT/TTS via streaming API** (locked decision) — self-hosting on a CPU VPS gives bad latency.
- **Same guardrails.** If a voice request implies an external action, it goes through the Phase 4
  approvals queue — voice does not get to send unattended.

---

## 5.1 Provider keys (BYO, in the encrypted .env)
```bash
GROQ_API_KEY=          # STT: Whisper-large via Groq — fast + cheap
# or DEEPGRAM_API_KEY=  # alternative streaming STT
ELEVENLABS_API_KEY=    # TTS
VOICE_STT=groq_whisper
VOICE_TTS=elevenlabs
```
Re-encrypt with SOPS after editing (`sops --encrypt ... > secrets/.env.enc`).

## 5.2 Voice endpoint on the agent
Add `POST /voice` to the agent service (tailnet-only, behind Caddy):
```
audio in ──▶ STT (streaming) ──▶ agent.run({session_id, namespace, text}) ──▶ reply text ──▶ TTS ──▶ audio out
```
- Reuse the exact `agent.run` path from Phase 3 — do **not** fork a second agent loop.
- Accept `session_id` so voice continues an existing thread (e.g. `jake:planning:daily`).
- Stream STT partials and start TTS on first sentence to cut perceived latency.

## 5.3 Clients (push-to-talk)
- **iPhone / iPad:** an Apple **Shortcut** — "Record Audio" → POST to
  `https://aios-jake.<tailnet>.ts.net/voice` → "Play" the returned audio. Tailscale must be on.
  Bind it to the Action Button / Back Tap for hold-to-talk feel.
- **Mac / Linux:** a hotkey script — `arecord`/`sox` to capture while a key is held, `curl` to the
  endpoint, `ffplay`/`afplay` to play the reply. ~30 lines.
- **Any device:** a minimal **PWA** (mic record → fetch → audio playback) served by Caddy on the
  tailnet, so devices without a native client still work.

## 5.4 Shared memory (the point)
Use a stable, device-agnostic `session_id`. Start a thread by text on the Mac, continue by voice on
the phone with the same id → the agent has full context. Confirm this explicitly in testing.

## 5.5 Latency
Push-to-talk target: **< 2–3 s** from release to first audio. Levers: streaming STT, first-sentence
TTS, keep the agent warm (no cold container). Measure and log round-trip; if it's bad, fix the
pipeline before adding features.

## 5.6 Realtime (later — gated spike, do not start here)
Only after push-to-talk is solid. Realtime = streaming duplex audio + interruption/barge-in.
**Set a kill criterion up front:** if you can't get acceptable latency + interruption within N days,
stay on push-to-talk. Realtime is an optimization, never a blocker for the rest of the system.

## 5.7 Security / privacy
- Raw audio leaves the box to the STT/TTS API (accepted tradeoff per the STT decision). Revisit
  self-hosted Whisper only if raw-audio privacy becomes a hard requirement.
- Endpoint tailnet-only + auth (same as Phase 3). Re-run the public-IP `nc` refuse test.
- Voice-triggered actions still funnel through the Phase 4 approvals queue.

## 5.8 Backups
Nothing new — voice transcripts are written to the vault like any other note and are already covered
by restic.

---

## Acceptance criteria (Phase 5 done)
- [ ] Speak from the phone (push-to-talk) → get a spoken answer over the tailnet.
- [ ] A thread started by text continues by voice on another device (shared session proven).
- [ ] Round-trip latency measured and within target (or a clear plan to close the gap).
- [ ] A voice request that implies sending something lands in the approvals queue, not sent directly.
- [ ] Public-IP `nc` refuse test still passes.

## Next (Phase 6 preview)
Productize: bake a Packer golden image, make bootstrap+customize idempotent, and do a clean-room
dry-run deploy to a throwaway VPS as a fake customer — proving the template spins up with zero
tenant-zero data leakage.
