# personal-ai-os — Session Handoff
**Date**: 2026-06-30  
**Session**: Tailscale+Mullvad networking fix + Phase 3 verification

---

## Current System State

### VPS (Hetzner CPX41)
- **Public IP**: 178.156.169.121  
- **Tailscale IP**: 100.69.188.122  
- **Hostname**: `aios-jake-1.tail828365.ts.net`  
- **SSH**: `ssh -i ~/.ssh/aios aios@178.156.169.121`  
- **Stack**: Docker Compose running — Caddy, agent (FastAPI/Claude), Nextcloud, Postgres, Nango (restarting)
- **Agent health**: `curl https://aios-jake-1.tail828365.ts.net/health` → `{"status":"ok","model":"claude-sonnet-4-6"}`
- **Agent UI**: `https://aios-jake-1.tail828365.ts.net/` (Tailscale HTTPS via `tailscale serve`)

### Fedora (local machine)
- **Tailscale IP**: 100.110.65.124 (`jakeos.tail828365.ts.net`)
- **Mullvad VPN**: Connected, exit Miami (45.134.142.199)
- **SSH tunnel**: `localhost:8443 → VPS:8080` via `~/.config/systemd/user/aios-tunnel.service`
- **AIOS access via tunnel**: `http://localhost:8443` ✓ working

---

## The Mullvad + Tailscale Problem (RESOLVED 2026-06-30)

### Actual root cause (not what it first looked like)
Two layered bugs, both needed fixing:

1. **Routing**: Mullvad's own `ip rule` catch-all (`not from all fwmark 0x6d6f6c65 lookup <mullvad-table>`) was being evaluated *before* the Tailscale-CGNAT rule (`from all to 100.64.0.0/10 lookup 52`), so all traffic to `100.64.0.0/10` — including the VPS — was routed out `dev wg0-mullvad` instead of `dev tailscale0` and never reached Tailscale at all. Confirmed with `ip route get 100.69.188.122` showing `dev wg0-mullvad`.
2. **Firewall** (secondary, only matters once routing is fixed): Mullvad's `inet mullvad` nftables table (`policy drop` on both `output` and `input`) has no exception for `tailscale0`, and Tailscale's own `ip filter` table has a `ts-input` chain with a catch-all `iifname != "tailscale0*" ip saddr 100.64.0.0/10 drop` that also needed broadening.

Pings worked throughout because `tailscale ping` uses a different, already-marked path; only TCP application traffic hit the routing bug.

### Critical gotcha: Mullvad's `ip rule` priorities are NOT stable
Mullvad renumbers its own catch-all rule's priority on every reconnect with no fixed range — observed values `5205/5206`, then `5198/5199`, then `8/9` across three consecutive reconnects in the same session. **A static priority for the Tailscale rule will eventually lose the race.** The fix must compute Mullvad's current priority at runtime and place the Tailscale rule one below it, every time.

### Fix applied
1. `ip rule`: dynamically computed priority, always `(Mullvad's current catch-all priority) - 1`.
2. `inet mullvad` nftables table: `oif "tailscale0" accept` inserted into both `output` and `input` chains.
3. `ip filter` table, `ts-input` chain: `ip saddr 100.64.0.0/10 accept` inserted (source-only match, not interface-gated).
4. **Persistence**: systemd timer `ts-mullvad-reconcile.timer` (every 20s, `OnBootSec=15s`) runs `/usr/local/bin/ts-mullvad-reconcile.sh`, an idempotent reconciler that re-applies all three fixes above, recomputing the `ip rule` priority fresh each run. Verified end-to-end: `mullvad disconnect` → `mullvad connect` → within one timer tick, routing/firewall/TCP connectivity all self-heal with zero manual intervention.
5. The old `/usr/local/bin/ts-mullvad-fix.sh` + `tailscaled.service.d/mullvad-compat.conf` (INPUT-chain-only, wrong layer) is now superseded by the reconciler but left in place — harmless, redundant.

**Verified working**: `curl -sk https://aios-jake-1.tail828365.ts.net/health` → `{"status":"ok","model":"claude-sonnet-4-6"}` directly over Tailscale (no SSH tunnel needed), survives Mullvad reconnect.

---

## SSH Tunnel (Working Workaround)

While Tailscale TCP is broken, AIOS is accessible at:
- **URL**: `http://localhost:8443` on Fedora
- **Tunnel**: `~/.config/systemd/user/aios-tunnel.service` (auto-restarts)
- **Start**: `systemctl --user start aios-tunnel.service`
- **Enable on login**: `systemctl --user enable aios-tunnel.service`

The systemd service tunnels `localhost:8443 → 178.156.169.121:8080` (Caddy) via SSH.

---

## Phase Status

| Phase | Status | Notes |
|-------|--------|-------|
| 0 — VPS provision | ✅ Done | Hetzner CPX41, cloud-init, Tailscale |
| 1 — Docker stack | ✅ Done | Caddy, Nextcloud, agent, Postgres |
| 2 — Nextcloud vault | ✅ Done | Nextcloud running, Obsidian vault sync config ready |
| 3 — Agent core | ✅ Done | FastAPI + Claude sonnet-4-6, SQLite sessions, vault reads |
| Tailscale TCP from Fedora | ✅ Done | `ip rule` priority race + nftables gaps fixed; `ts-mullvad-reconcile.timer` makes it durable across reconnects |
| Phase 3 — onboarding interview | ✅ Done 2026-07-01 | `/vault/context/` filled — see below |

### Phase 2 Remaining
- Install Nextcloud desktop sync on Mac
- Point Obsidian at the synced vault folder

### Phase 3 Remaining
- None. Onboarding interview complete (see "Onboarding interview" below).

**Onboarding interview (2026-07-01):** No `onboarding-interview` skill exists yet (`skills/`
only has a README describing it) — ran the interview directly instead. Also found and fixed a
case-sensitivity bug: `agent/vault.py` reads `/vault/context/` (lowercase), but the vault only
had an empty `/srv/aios/vault/CONTEXT/` (uppercase) — removed the stale empty dir and created
the correct lowercase one. Wrote `about-me.md`, `working-style.md`, `brand-voice.md` with
drafted content (from known context, confirmed with Jake before writing). `voc.md` left
intentionally blank — it captures real customer-quote language for client-facing work, and none
has been captured yet; do not fabricate it. Verified live via
`docker exec platform-agent-1 cat /vault/context/about-me.md` — the bind mount picks up changes
without a container restart. The agent no longer falls back to `(not yet set)` for these three
files.

### Phase 4 (Not started)
- Intake service (Recall.ai/Otter webhooks)
- MCP connectors (Gmail/Calendar via Nango)
- Personas / specialized agents
- ~~Fix Nango container~~ ✅ Fixed 2026-06-30 — see below

**Nango container fix (2026-06-30):** It was crash-looping on `getaddrinfo ENOTFOUND nango-db` —
the image defaults to a DB host of `nango-db` when `NANGO_DB_*` env vars aren't set, and this
stack never set them (every service shares one `../.env` via `env_file:`, which has Nextcloud's
Postgres vars but nothing Nango-specific). Fix: created a dedicated `nango` database in the
existing `platform-db-1` Postgres instance (owned by the `nextcloud` superuser role — this
instance only ever had one DB before), and added to `.env`:
```
NANGO_DB_HOST=db
NANGO_DB_PORT=5432
NANGO_DB_USER=nextcloud
NANGO_DB_PASSWORD=<same as NEXTCLOUD_DB_PASSWORD / POSTGRES_PASSWORD>
NANGO_DB_NAME=nango
NANGO_DB_SSL=false
```
**Second gotcha hit while fixing this**: `docker compose up -d nango` from `platform/` failed
with `invalid spec: :/vault: empty section between colons` — Compose auto-loads `.env` for
`${VAULT_PATH}}`-style file interpolation only from its own working directory, not from the
`../.env` that `env_file:` points services at. Every future `docker compose` invocation on this
box **must** pass `--env-file ../.env` explicitly, e.g.:
```bash
cd /home/aios/personal-ai-os/platform && docker compose --env-file ../.env up -d
```
Nango is now up, migrated its schema, and listening on :3003 (proxied internally). Confirmed
stable for 60s+ post-recreate; Nextcloud's Postgres data survived the `db` container recreation
(same-name/same-hash env change triggered it too) since it's on the persistent `db_data` volume.

---

## Key Files

| Path | Purpose |
|------|---------|
| `~/personal-ai-os/platform/docker-compose.yml` | Main stack |
| `~/personal-ai-os/platform/caddy/Caddyfile` | Reverse proxy routes |
| `~/personal-ai-os/platform/agent/app.py` | FastAPI agent |
| `~/personal-ai-os/infra/terraform/` | Hetzner infra (firewall open to 0.0.0.0/0) |
| `~/.ssh/aios` | VPS SSH key |
| `~/.config/systemd/user/aios-tunnel.service` | SSH tunnel service (fallback; no longer required day-to-day) |
| `/usr/local/bin/ts-mullvad-reconcile.sh` | **Current fix.** Idempotent: recomputes `ip rule` priority + reapplies nft accepts for `tailscale0` every run |
| `/etc/systemd/system/ts-mullvad-reconcile.{service,timer}` | Runs the reconciler every 20s, `OnBootSec=15s` |
| `/tmp/fix-mullvad-ts.sh` | Diagnostic script used during troubleshooting (superseded, kept for reference) |
| `/usr/local/bin/ts-mullvad-fix.sh` + `tailscaled.service.d/mullvad-compat.conf` | Old INPUT-chain-only fix (superseded by the reconciler, harmless left in place) |

---

## Continuing Work

Tailscale-over-Mullvad is fixed and self-healing. Nothing pending here.

**Quick health check**:
```bash
curl -sk https://aios-jake-1.tail828365.ts.net/health
# Expected: {"status":"ok","model":"claude-sonnet-4-6"}
```

**Reconciler status** (if Tailscale TCP ever seems to regress again):
```bash
systemctl status ts-mullvad-reconcile.timer
sudo systemctl start ts-mullvad-reconcile.service   # force an immediate reconcile
ip rule show | grep 100.64                          # our rule should sit one priority below Mullvad's catch-all
```

**VPS quick checks**:
```bash
ssh -i ~/.ssh/aios aios@178.156.169.121 "cd ~/personal-ai-os/platform && docker compose --env-file ../.env ps"
```

**Next real work item**: Phase 2 remaining — install Nextcloud desktop sync on Mac and point Obsidian at the synced vault folder. Phase 3 is fully done; Phase 4 (intake service, MCP connectors, personas) is next after that.
