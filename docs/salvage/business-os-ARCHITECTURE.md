# Architecture & decisions

Why the Business OS is built the way it is, and how to extend it. Companion to `README.md`.

## North star

Stage 5 (AI-Native) of the GTM maturity model: AI agents own routing, lead-scoring, and
orchestration across channels; campaigns self-optimize. We get there by **integrating** mature
OSS for the commodity layers (CRM, BI, workflow, scheduling) and spending our build budget only
on the connective tissue (the cockpit) and the AI layer (n8n + Claude skills + loops).

This is the natural next step of `~/claude-jake-os/ARCHITECTURE-v2.md`: revenue-first, one spine,
one design system, generated-not-hand-maintained — now running as a real server, not local static HTML.

## Key decisions

**Hetzner + Cloudflare Tunnel, not Cloudflare-native.** The workload is persistent, stateful,
multi-service Docker — VPS-shaped. Cloudflare's compute is serverless (Workers = ms CPU budgets;
Containers = small, scale-to-zero, single-image), so running off-the-shelf OSS there would mean
re-platforming everything. A flat VPS is cheaper for always-on, lets us "add RAM by rebooting,"
and reuses the company-brain pattern. Cloudflare does what it's best at: the free, secure edge.

**Zero-dependency cockpit (stdlib http.server), not FastAPI.** The plan said FastAPI+HTMX; we kept
HTMX on the front but built the backend on the stdlib, matching `dashboard.py`/`os_home.py`. Result:
a tiny container, no dependency tree to patch, and it runs locally with `python3 app.py` for instant
verification. It can graduate to FastAPI if forms/auth/async outgrow the stdlib — the data layer
(`data.py`) is already framework-agnostic.

**cloudflared maps hostnames → services directly; no Caddy.** Cloudflare terminates TLS and the
tunnel's ingress routes each Public Hostname to a container. One fewer moving part and less RAM.
(An infra-as-code alternative using a config file lives in `cloudflared/config.example.yml`.)

**Two databases.** Postgres for n8n/Metabase/Cal.com (all first-class Postgres). EspoCRM speaks
MySQL/MariaDB, so it gets its own MariaDB. Metabase reads the shared Postgres the others write to,
which is what makes it the Scorecard surface.

**Cockpit state in its own SQLite, not Postgres.** Rocks/L10/to-dos/metrics live in a small SQLite
file on a volume — keeps the cockpit zero-dependency and decoupled. Promote to Postgres if Metabase
needs to chart cadence data directly.

## Data flow

```
prospects.json ─┐                         ┌─ Home KPIs / Pipeline (read)
(prospect.py)   ├─► cockpit (read-only) ──┤
knowledge.db ───┘                         └─ Knowledge search (FTS5)

Cal.com booking ─► n8n ─► EspoCRM contact + confirmation        (phase 2)
EspoCRM stage   ─► n8n ─► Listmonk email / Metabase refresh      (phase 2/3)
CRM/registry    ─► Metabase ─► Scorecard numbers                 (phase 3)
signals         ─► n8n + Claude skills ─► lead score / routing   (phase 4 = Stage 5)
```

One source of truth stays on the laptop (the GTM registry + knowledge spine); `scripts/sync-data.sh`
pushes it to the box read-only. The cockpit never duplicates it.

## How to add a service (the pattern)

1. Add the service to `docker-compose.yml` (own DB on Postgres or MariaDB as needed; volume for state).
2. Add its env/secret to `.env.example`.
3. Add a Public Hostname in the Cloudflare tunnel (`sub.<DOMAIN>` → `http://service:port`) + an Access policy.
4. Add a tile to `SERVICE_LINKS` in `cockpit/data.py` so it appears in the Apps launcher.
5. Wire it into n8n for cross-app automation.

Worked examples for phase 2: **FreeScout** (helpdesk, <1GB, own MariaDB or shared), **Listmonk**
(email, ~57MB, needs SMTP relay), **Vikunja/Plane** (projects).

## Resource budget (16GB CAX31)

postgres ~0.3 · mariadb ~0.4 · redis ~0.05 · espocrm ~0.4 · metabase ~2 · n8n ~0.5 · calcom ~1.5 ·
cockpit ~0.1 · cloudflared ~0.05  →  ~5.3GB. Plenty of headroom; phase-2 additions fit. When it
gets tight, resize to CAX41 (32GB) with a reboot.

## Phase 4 — the AI-Native layer (Stage 5)

The endgame, all orchestrated through n8n + Claude skills (adapting `~/self-improving-loop`):
- **Lead scoring** — score inbound + registry prospects on gap/value/intent signals.
- **Signal-triggered routing** — new review, site-down, form-fill → the right workflow fires.
- **Auto-drafted outreach** — generate per-prospect pitches (reuse `prospect.py pitch`) for human approval.
- **Self-optimizing** — a verify-loop that measures reply/booking rates and tunes the playbooks.
