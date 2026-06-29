# Personal AI OS — Plan & Wireframe (v3)

**Date:** 2026-06-29
**Owner:** Jake
**Status:** Planning — now scoped as a deployable product, not just a personal setup

> Changes from v2: reframed as a **templatized, multi-deploy product** you can spin up for customers. Added the **Productization** section (platform-vs-tenant split, repo structure, deploy flow, customization via the onboarding skill), an optional **Remote GUI** note, and a revised **Phase 0** built around "customer zero is you."

---

## What you're actually building

Two things at once, and the second is the bigger one:

1. **For you:** a persistent, server-side Claude agent reachable from every device — second brain, executive assistant, tutor, trainer, coach — with voice, an Obsidian second brain, and a capture layer that turns meetings and voice notes into actions.
2. **As a product:** a **reproducible template** you can deploy on a fresh VPS for any small-business customer in minutes and customize by *conversation*, not config editing. This is the agency offer — sovereign AI ops, one box per client.

You are **tenant zero**: the first deployment of the generic template, not a special hand-built box you later try to genericize.

---

## The one principle that makes it productizable

**Separate the platform from the tenant config.** Everything reusable is identical across every deployment; everything specific is injected.

| Platform (generic, in the repo/image) | Tenant config (per deployment, injected) |
|---|---|
| Agent core, intake/normalizer, Nango, Nextcloud, Caddy, session DB | Vault *content*, context files, persona prompts |
| Bundled skills | Connector tokens / which connectors are on |
| Compose files, IaC, runbooks | Customer name, domain, branding |
| Secrets *scaffolding* (placeholders) | Actual secrets (generated at provision) |

Get this split clean and "spin up for a new customer" = provision a box + inject a new tenant config. Get it muddy and every customer is a custom build.

---

## Productization — templatized deploy (new)

### The repo *is* the product (your "build files, instructions, included skills")

A single git monorepo is the source of truth. Sketch:

```
personal-ai-os/
├─ README.md                 # what it is + deploy in 3 commands
├─ infra/
│  ├─ terraform/             # hcloud: VPS, volume, firewall, private net
│  └─ cloud-init.yaml        # first boot: user, ssh, tailscale, docker
├─ platform/                 # the GENERIC stack — identical everywhere
│  ├─ docker-compose.yml     # agent · intake · nango · nextcloud · caddy · db
│  ├─ agent/                 # Claude Agent SDK service
│  ├─ intake/                # capture webhook + normalizer
│  └─ caddy/                 # reverse proxy (templated)
├─ skills/                   # bundled skills (see below)
├─ templates/                # per-tenant TEMPLATES — no real data
│  ├─ context/               # about-me · brand-voice · working-style · voc (blank)
│  ├─ tenant.yaml.example    # name, domain, connectors enabled
│  └─ .env.example           # secret placeholders
├─ scripts/
│  ├─ bootstrap.sh           # provision → secrets → stack up
│  └─ customize.sh           # run onboarding interview → fill tenant config
└─ docs/                     # runbooks + instructions
```

Containerized (Docker Compose) on purpose: the platform is **provider-agnostic**, not Hetzner-locked. "New VPS" is trivial on any host.

### Two snapshot layers — fast path + rebuild path

- **Golden image (Hetzner snapshot, built with Packer from the repo):** OS + Docker + pre-pulled images. Spin-up in **minutes**. The fast path for new customers.
- **The repo (IaC):** source of truth that *regenerates* the golden image. Never depend on an opaque snapshot you can't rebuild — the repo is the truth, the image is a cache.

### Deploy flow (target: minutes, not a day)

1. **Provision** — `terraform apply` (or restore the golden snapshot) → bare VPS with Docker + Tailscale, firewalled, tailnet-only.
2. **Bootstrap** — `bootstrap.sh` → generate per-tenant secrets (SOPS/age), bring up the platform stack.
3. **Customize** — `customize.sh` runs the **onboarding interview skill**: *who are you, what does your business do, what are your headaches, which tools do you use* → writes the customer's context files, seeds initial workflows, flags which connectors to enable.
4. **Connect** — customer authorizes their tools via the MCP-first flow (single browser login each).

### Customization is conversational — that's the elegant part

That interview skill you got is the **customization engine**. Every deployment ships the *same* image; the interview is what personalizes it. No per-customer YAML surgery — you (or the customer) talk to it and it writes the config. The fastest possible "customize" step is a conversation the platform already knows how to have.

### Skills to bundle in the image

- **Onboarding interview** (`cowork-onboarding`-style) — the customization engine; produces context files + starter workflows.
- **`prime`** — loads all context at session start; a sane default for every tenant.
- **`self-assessment`** — finds each customer's highest-ROI automations; doubles as your agency discovery/upsell tool.
- **`plugin-customizer` / `create-plugin`** — when a customer needs bespoke skills, package them as a per-tenant plugin instead of forking the platform.
- **Optional SMB pack** — the small-business skills (invoice-chase, lead-triage, month-end, etc.) for customers who want them, off by default.

---

## Business-model decisions (locked)

1. **Deployment unit — one VPS per customer.** Clean isolation, each client owns their data and box, and it *is* the sovereignty pitch you're selling. Multi-tenant on one box is cheaper but undercuts the story and tangles data. Templatize the single-VPS unit.
2. **API keys — bring-your-own for v1.** Customers supply their own Claude/STT/Recall keys (no metering, they own the bill). "You provision and meter" becomes a managed upsell later.
3. **Sizing — CPX41 (16 GB) for tenant-zero (your box);** you want GUI headroom and it's the build/template machine. **CPX31 (8 GB) as the floor** for lightweight customer deploys; size up per customer need.

---

## Decisions (locked)

| Area | Decision |
|---|---|
| File/sync | **Nextcloud** (files + vault); agent writes vault via **git** to avoid conflicts |
| Brain | **Claude Agent SDK, headless service on the VPS** |
| Agent shape | **One agent, multiple modes** (prompts + skill packs + thread namespaces) |
| Connector auth | **MCP-native → self-hosted Nango → hand-roll. No Composio in the hot path.** |
| Meeting capture | **Prove with Otter MCP → consolidate on Recall.ai** |
| Voice notes | **Reuse the VPS STT pipeline** |
| Voice agent | **Push-to-talk MVP first, realtime later** |
| STT/TTS | **Streaming API** (Groq Whisper / Deepgram / ElevenLabs) |
| Tutor | **Split:** server voice-tutor persona + spaced repetition; keep interactive `/teach` for the Mac |
| Packaging | **Git monorepo + Docker Compose + IaC + golden image; customer-zero-is-you** |

---

## Capture Layer

**Principle: decouple capture from processing.** One intake; the agent processes anything that lands there; sources swappable.

```
Recall.ai (meetings) ─webhook─┐
tl;dv (optional)     ─webhook─┤
Otter (MCP pull)     ─────────┼─▶  /intake + normalizer ─▶ /Inbox/transcripts/ ─▶ agent:
Voice note (phone)   ─audio───┤                            (normalized .md)        extract actions →
Voice note (Mac/Lx)  ─STT─────┘                                                    draft email (Gmail MCP)
                                                                                   propose event (Cal MCP)
                                                                                   file note → you approve
```

### Normalized transcript schema (Markdown + YAML frontmatter)

```markdown
---
id: 2026-06-29-acme-kickoff
source: recall            # recall | tldv | otter | voicenote
type: meeting             # meeting | voice_note
title: Acme kickoff call
started_at: 2026-06-29T15:00:00Z
ended_at: 2026-06-29T15:42:00Z
participants: [jake, dana@acme.com]
context: business         # personal | business | <project>
status: raw               # raw | processed
---
## Transcript
[00:00] Dana: ...
## Agent output
summary: >
action_items: [...]
proposed_calendar: [...]
proposed_emails: [...]
```

Sources by lift: **Otter MCP** (already connected — prove the loop now) → **Recall.ai** ($0.50 + $0.15/recording-hr, no platform fee, 7-day free storage — pull promptly) → voice notes on the shared STT pipeline.

---

## Auth & Connectors

"Auth once" = OAuth 2.1 auth-code + PKCE. No broker needed.

1. **MCP-native first** — single browser login, host holds + refreshes token. Free, sovereign, the Nov-2025 MCP default. How Gmail/Calendar/Otter already connected.
2. **Self-hosted Nango** — for REST-only apps; free self-hosted auth + proxy (~800 APIs), OAuth + refresh + encrypted credential store on *your* box. Optionally wrap as a thin local MCP.
3. **Hand-roll** — auth-code+PKCE + token table + refresh worker, only for true oddballs.

**Token vault (ties to Phase 1):** master secrets in **SOPS+age** (or Vault), injected as env, never in vault/git. MCP tokens persisted to the same store. Nango keeps its own encrypted Postgres credential DB. Backups encrypt the token store; intake + Nango UI are tailnet-only.

**Composio stays out of the hot path** — free tier is real (20k calls/mo) but it holds tokens server-side and was **breached May 21 2026** (~5,241 API keys + 5,001 GitHub tokens exfiltrated via one employee's Gmail token). Counter to the whole sovereignty thesis. Prototyping only.

---

## Remote GUI (optional)

Keep the VPS **headless by default**; bring up a desktop only when needed. Install lightweight XFCE, don't autostart a heavy session. Access **tailnet-only — never expose RDP/VNC publicly**:

- **NoMachine** (recommended) — free, snappiest, native Mac/Linux clients. Best for real desktop work.
- **xrdp** — standard RDP; Microsoft Remote Desktop / Remmina.
- **Apache Guacamole** — browser-based, zero install; fits "from any device/tablet." Slightly less crisp.

Default: NoMachine over Tailscale; add Guacamole later if tablet/no-install access matters. Heavy browser GUI use is the main reason to start at **CPX41 (16 GB)** over CPX31.

---

## Build sequence (bottom-up)

**Phase 0 — Template scaffold + stack inventory.** Stand up the **git monorepo** skeleton (the structure above) and document what's already on your Mac/Linux laptop (tools, vault layout, scripts, connectors). Decide platform-vs-tenant boundaries up front. *Output: repo skeleton + stack inventory.* This is where "customer zero is you" starts — you're authoring the template, then deploying onto it.

**Phase 1 — Foundation + secrets (codified as IaC).** Terraform + cloud-init to provision and harden (firewall, SSH keys, Tailscale, auto-updates, encrypted backups) + the **token vault** (SOPS+age). Everything as repo code so it's repeatable for customer #2.

**Phase 2 — Cloud + vault.** Nextcloud + Obsidian vault (git-write), synced to all devices; conflict-tested. In the image as a service.

**Phase 3 — Agent core.** Headless Claude agent + SQLite session store over the tailnet; prove "pick up where I left off" across two devices.

**Phase 4 — Connectors + Capture + personas.** MCP-first → Nango; intake + normalizer; prove the meeting loop on **Otter MCP**, then **Recall.ai**; EA + second-brain + tutor/coach personas. Build the transcript-to-action loop first — highest-value proof.

**Phase 5 — Voice.** Push-to-talk MVP (shared STT), then iterate toward realtime if it earns its keep.

**Phase 6 — Productize.** Bake the golden image (Packer), write `bootstrap.sh` + `customize.sh`, dry-run a clean deploy to a throwaway VPS, run the onboarding interview as if you were a new customer. When that works, you can sell it.

Each phase is independently useful; stop after Phase 3 and you have a server-side second brain.

---

## Cost & sizing (approximate — verify at provisioning)

- **VPS:** Hetzner CPX31 (4 vCPU / 8 GB) ≈ €15–16/mo to start; **CPX41 (16 GB)** if you want desktop-GUI headroom or run heavier per-customer. LLM is API-side.
- **Tailscale / Caddy / Nango / SOPS / Packer:** free.
- **Claude API:** ~$20–100/mo per active instance, usage-based.
- **STT/TTS:** ~$5–25/mo light use. **Recall.ai:** $0.65/recording-hr only when recording.
- **Per-customer economics:** roughly box + API + capture usage. Price the offer above that with margin — your pitch is sovereign, isolated, customized-by-conversation AI ops.

---

## Next moves

1. Confirm the **two business-model forks** (one-VPS-per-customer? BYO API keys?) and give a **budget ceiling** (sets CPX31 vs CPX41).
2. Then I'll either **scaffold the repo skeleton** (Phase 0) or write the **Phase 0+1 runbook** — your call which first.

I can scaffold the monorepo skeleton now regardless of the budget answer, since it's all structure and placeholders. Say the word.
