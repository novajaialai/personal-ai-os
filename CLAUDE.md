# CLAUDE.md — Personal AI OS (project handoff)

> **Read this first.** It's the single source of truth for working on this project — for the
> coding agent *and* the human at the terminal. Full reasoning lives in `docs/brief.md`;
> the executable build steps live in `docs/runbook-phase0-1.md`.

**Status (2026-06-29):** Planning complete. Repo skeleton built. Phase 0–1 runbook ready.
**Building has not started.** Next action is Phase 0, step 0.1 (see "Next" below).

---

## Mission

Build a **sovereign, self-hosted personal-and-business AI operating system**: one persistent
Claude agent (second brain, executive assistant, tutor, trainer, coach) running on a VPS,
reachable from phone/tablet/Mac/Linux, that remembers context across devices, talks by voice,
uses an Obsidian vault as its memory, and turns meetings + voice notes into actions.

It is built as a **deployable product**, not a one-off box. The owner (Jake) is **tenant zero** —
the first deployment of a generic template that later spins up for small-business customers,
one VPS per customer, customized by conversation.

---

## How to work on this project (operating style)

- **Plan before executing anything non-trivial.** Show the plan, get approval, then build.
- **Be opinionated.** If there's a better way, say so and push back — don't just agree.
- **Show reasoning** — the "why," not just the "what."
- **Concise and direct.** No fluff, no filler, no padding.
- **No emoji** unless Jake uses them first.
- Jake is technically strong (Linux, bash, cron, billing/CRM ops). Use real commands and
  implementation detail; assume he can read and run code.

---

## Locked decisions — do not re-litigate

| Area | Decision |
|---|---|
| Deployment unit | **One VPS per customer.** Jake's box (tenant zero) = Hetzner **CPX41** (16GB). Customer floor = CPX31. |
| API keys | **Bring-your-own per tenant** for v1. Provision-and-meter is a later managed upsell. |
| File/sync | **Nextcloud** = device-sync transport for files + vault. **Agent writes via WebDAV** (single coordinator). **git** = hourly server-side history/rollback snapshot, not the sync path. |
| Brain | **Claude Agent SDK**, headless service on the VPS. One agent, multiple modes (prompt + skill pack + thread namespace). |
| Memory | Obsidian vault = long-term; **SQLite** session store = mid-term ("pick up where I left off"). |
| Connector auth | **MCP-native first → self-hosted Nango → hand-roll.** **No Composio in the hot path** (breached May 2026; violates sovereignty). |
| Meeting capture | Prove the loop with **Otter MCP** (already connected) → consolidate on **Recall.ai** (webhook → VPS). |
| Voice notes | Reuse the VPS **STT pipeline** (Groq Whisper / Deepgram), not a meeting tool. |
| Voice agent | **Push-to-talk MVP first**, realtime later (treat realtime as a spike with a kill criterion). |
| STT/TTS | Streaming **API** to start (not self-hosted on CPU). |
| Tutor | Split: server voice-tutor persona + spaced repetition; keep interactive `/teach` for the Mac. |
| Packaging | Git monorepo + Docker Compose + IaC + golden image. **Customer-zero-is-you.** |
| Budget | ~$20–100/mo all-in for tenant zero. Infra ≈ $17/mo fixed; rest is API headroom. |

---

## Hard guardrails (security + correctness — never violate)

1. **Tailnet-only.** Nothing is exposed to the public internet. Access is via Tailscale. Host
   firewall default-denies inbound except on `tailscale0`.
2. **Docker bypasses UFW.** Docker writes its own iptables rules. **Every published port must bind
   to the box's Tailscale IP (`${TAILSCALE_IP}`), never `0.0.0.0`.** Verify with `nc` against the
   public IP — it must refuse.
3. **Secrets discipline.** Real secrets never land in git as plaintext. Use **SOPS + age**;
   decrypt-at-deploy on the box only. The age private key + restic passphrase live off-box in a
   password manager. `.gitignore` blocks `.env`, `secrets/`, `*.tfvars`, `*.tfstate`.
4. **Backups must be tested.** A restic restore must succeed before the box is trusted.
5. **Platform vs tenant split.** Nothing in `platform/`, `infra/`, or `skills/` may contain tenant
   data. Tenant-specific values live only in injected config (`.env`, `tenant.yaml`, vault content).
6. **Approvals before sends.** The agent drafts emails and proposes calendar events; a human
   approves before anything goes out. No unattended external actions.
7. **Infra is code.** Changes go through Terraform/compose in the repo. `terraform plan` shows no drift.

---

## Architecture (one screen)

```
Devices (phone/tablet/Mac/Linux)
        │  Tailscale private mesh (no public exposure)
        ▼
Caddy reverse proxy (TLS, bound to Tailscale IP)
        │
        ├── Agent core (Claude Agent SDK) ── reads/writes ── Obsidian vault (git) ── SQLite sessions
        ├── Intake (capture webhook + normalizer) ── writes ── /vault/Inbox/transcripts/
        ├── Nango (self-hosted OAuth broker, encrypted token store)
        └── Nextcloud (files + vault sync)
        ▼
Security & Ops base: UFW default-deny · SOPS+age secrets · restic encrypted backups · unattended-upgrades
```

Capture flow: `Recall.ai / tl;dv / Otter / voice-note STT → /intake → normalized transcript in vault → agent extracts action items → drafts email (Gmail MCP) + proposes event (Calendar MCP) → human approves.`

---

## Repo map

```
personal-ai-os/
├─ CLAUDE.md                 # this file
├─ README.md                 # what it is + deploy in 3 steps
├─ infra/terraform/          # hcloud VPS, volume, default-deny firewall
├─ infra/cloud-init.yaml     # first boot: user, ssh, tailscale, docker, ufw
├─ platform/                 # GENERIC stack (identical every deploy)
│  ├─ docker-compose.yml     # agent · intake · nango · nextcloud · caddy · db
│  ├─ caddy/Caddyfile
│  ├─ agent/                 # Agent SDK service (stub → Phase 3)
│  └─ intake/                # capture + normalizer (stub → Phase 4) + transcript.schema.md
├─ skills/                   # bundled skills (onboarding-interview = customization engine, prime, ...)
├─ templates/                # per-tenant TEMPLATES (context/, tenant.yaml.example, .env.example)
├─ scripts/                  # bootstrap.sh, customize.sh
└─ docs/                     # brief.md (reasoning), runbook-phase0-1.md (build steps), stack-inventory/
```

---

## Phase roadmap

0. **Template scaffold + stack inventory** ← current
1. **Foundation + secrets** (provision, harden, SOPS vault, tested backups)
2. Cloud + vault (Nextcloud transport + WebDAV agent writes + git history, synced, conflict-tested)
3. Agent core (headless Claude agent + SQLite sessions; prove cross-device resume)
4. Connectors + capture + personas (MCP-first → Nango; intake; Otter→Recall; EA/second-brain/tutor)
5. Voice (push-to-talk MVP → realtime later)
6. Productize (Packer golden image; bootstrap+customize; clean dry-run deploy)

Each phase is independently useful. Stop after Phase 3 and a server-side second brain already works.

---

## Next

Execute **Phase 0 → Phase 1** in `docs/runbook-phase0-1.md`. Immediate first command:

```bash
cd personal-ai-os
git init -b main && git add . && git commit -m "Scaffold Personal AI OS template"
# then create a PRIVATE remote and push; continue with runbook step 0.2
```

**Before provisioning (Phase 1) you need:** a Hetzner API token, a Tailscale account, an SSH keypair,
and an age keypair for SOPS. All listed under "Prerequisites" in the runbook.

**Open (non-blocking):** none. Budget and all forks are decided. Proceed.
