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
| 2 — Nextcloud vault | ✅ Actually done 2026-07-01 | Was marked done prematurely — vault wasn't exposed, then fixed, synced, and Obsidian confirmed pointed at it. See below. |
| 3 — Agent core | ✅ Done | FastAPI + Claude sonnet-4-6, SQLite sessions, vault reads |
| Tailscale TCP from Fedora | ✅ Done | `ip rule` priority race + nftables gaps fixed; `ts-mullvad-reconcile.timer` makes it durable across reconnects |
| Phase 3 — onboarding interview | ✅ Done 2026-07-01 | `/vault/context/` filled — see below |

### Phase 2 Remaining
- None. Nextcloud desktop sync installed on Mac, confirmed pulling real `Vault/` content, and
  Obsidian confirmed showing that vault (2026-07-01). Obsidian was pointed at
  `~/Library/CloudStorage/Nextcloud-jake@aios-jake-1.tail828365.ts.net/Vault` via
  `obsidian://open?path=...` (URI scheme, percent-encoded for the `@`) after directly editing
  `obsidian.json` didn't take effect on its own. Verification was done via a local Claude
  Code/Cowork instance running ON the Mac (with GUI/computer_use access there) — remote
  diagnosis from Fedora over SSH hit a real macOS wall: SSH sessions run in a separate
  non-GUI security session, so `screencapture` and any WindowServer-attached API fail
  regardless of TCC permissions granted, and `~/Desktop`/`~/Library/CloudStorage/.../Vault`
  contents are also TCC-protected from `sshd`-spawned processes. Worth remembering for future
  Mac-side debugging: don't fight SSH-based screen/file inspection past the TCC wall — hand off
  to a local agent instead.

**Nextcloud vault exposure fix (2026-07-01):** Setting up Mac desktop sync surfaced four
separate, real bugs — Phase 2 had been marked done without ever testing an actual client
connection end to end:

1. **Mac Tailscale DNS clobbered by Mullvad**: `tailscale status` showed
   `getDNSServers failed: Fallthrough, no resolvers found` — Mullvad's DNS override replaced
   Tailscale's MagicDNS resolver (`100.100.100.100`) and didn't restore it on disconnect, so
   `*.ts.net` hostnames stopped resolving even with Mullvad off. Fixed with
   `Tailscale down && Tailscale up` to force it to reassert its resolver config. **Not
   persistent** — no macOS equivalent of `ts-mullvad-reconcile.sh` exists yet; may recur on
   future Mullvad reconnects.
2. **Mullvad firewall blocks CGNAT even for split-tunnel-excluded apps**: separately from DNS,
   TCP connections to the VPS's Tailscale IP hung/timed out while Mullvad was connected, even
   for apps explicitly split-tunnel-excluded (`Tailscale.app`, `Nextcloud.app`). Same bug class
   as the Linux nftables issue above, different firewall engine (macOS `pf`) — root cause not
   fully diagnosed (needs interactive `sudo pfctl -sr`, which needs Jake at the keyboard).
   Workaround used: disconnect Mullvad during Nextcloud setup/sync.
3. **Caddy `/files` route never stripped its own prefix**: `platform/caddy/Caddyfile`
   proxied `/files/*` straight through to the Nextcloud container without stripping `/files`,
   and Nextcloud's `overwritewebroot` was never set — so Nextcloud received literal requests
   for `/files/status.php` etc., which don't exist internally, and 404'd (surfaced as a
   confusing `401` in the Nextcloud client). This is why manual browser access to `/files`
   "worked" (it tolerated root-relative absolute links) but the desktop/mobile sync clients
   could not. Fixed: `occ config:system:set overwritewebroot --value=/files` (+
   `overwrite.cli.url`, `overwriteprotocol=https`) on the Nextcloud side, and
   `uri strip_prefix /files` added to the Caddy `@nextcloud` block. Legacy unprefixed routes
   (`/status.php`, `/remote.php/*`, etc.) left in place as a harmless fallback.
4. **Stale admin password**: `.env`'s `NEXTCLOUD_ADMIN_PASSWORD` no longer matched the live
   Nextcloud account (only used by the Nextcloud image on first container init — a later
   recreate or manual change had drifted from it). WebDAV `PROPFIND` returned `401` even after
   fixing #3. Fixed with `occ user:resetpassword --password-from-env jake` to force it back in
   sync with `.env`.
5. **Vault External Storage mount existed but was never scanned**: a `Vault` local External
   Storage mount (→ `/srv/aios/vault`, applicable to all users) was already configured from an
   earlier session, but its contents never showed up over WebDAV (`PROPFIND` on `/Vault/`
   returned zero children) because Nextcloud's file-cache index was never populated for it.
   Fixed with `occ files:scan jake`. This is why a first full sync pulled Nextcloud's built-in
   demo content (`Documents/`, `Photos/`, `Templates/`, sample files) instead of the real vault
   — that demo content is harmless and lives in Nextcloud's own per-user storage, separate from
   `Vault/`; the sync client should be pointed at `Vault/` only via selective sync.

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

### Phase 4 (Started 2026-07-01: vault tool use)
- **Metabase admin login fix + Twenty CRM data source — DONE 2026-07-01.** Jake set a Metabase
  admin password during onboarding, then lost it (Google Password Manager didn't save it).
  This build's `reset-password` CLI tool (`java -jar metabase.jar reset-password <email>`) is
  reproducibly broken — reset it 3 separate times (once with a full container restart in
  between to rule out in-memory caching) and every generated password failed to authenticate.
  Manually reverse-engineering the bcrypt(salt+password) scheme from `core_user.password` /
  `password_salt` also failed (tried both salt+pw and pw+salt orderings, both `$2a$`/`$2b$`
  bcrypt variants). Root-caused as a genuine bug in this specific build (very recent —
  migration filenames reference preview MCP features dated April-June 2026). Fix: dropped and
  recreated the `metabase` Postgres database (nothing was in it yet — zero data loss), let
  Metabase re-run its first-boot setup fresh, and completed that setup via its own
  `POST /api/setup` REST endpoint with a password Jake controls
  (`yakobdart@gmail.com` / `aios-metabase-2026` — **he should change this**, since I set it and
  therefore know it). Also recreated the Twenty CRM database connection (host `twenty-db`, db
  `default`, user `postgres`) via `POST /api/database` — confirmed `initial_sync_status:
  complete`. Earlier UI attempts at this same connection also failed with "password incorrect",
  root-caused separately via Metabase's own logs to a leading space in the username field
  (` postgres` vs `postgres`) — a real, different bug from the account-login issue above, both
  hit in the same session.
- **Agent vault tool use — DONE 2026-07-01.** The agent was a plain chat completion wrapper
  (`app.py` called `client.messages.create()` with zero tool use); `vault.py`'s
  `write_to_inbox()` existed but was never invoked, and the system prompt's claimed
  capabilities were aspirational. Jake wants the agent to actually function as a
  Karpathy-style second brain — plain markdown, agent reads/writes/searches directly, no
  vector DB, and critically **Jake never opens Obsidian himself; chat is the only interface**.
  Built: `vault.py` gained `list_notes()`, `search_notes()` (grep-based), `read_note()`,
  `write_note()`, `append_note()` (timestamped log entries), all path-guarded to stay inside
  `/vault`. `app.py` now runs a real Claude tool-use loop (up to `MAX_TOOL_ROUNDS=8`) instead
  of a single completion call. `prompts.py` rewritten to describe actual tools instead of
  aspirational prose. No infra changes needed — vault was already bind-mounted read/write into
  the agent container. Verified end-to-end in production: `list_notes`+`read_note` correctly
  read real context files; `write_note`/`append_note` created a real timestamped file on disk
  (confirmed via `docker exec ... cat`, then removed — it was test content, not real); `search_notes`
  found it via grep. The Nextcloud↔Mac Obsidian desktop sync from earlier today still runs but
  is no longer part of the design — it was Jake's original ask, but he decided he doesn't want
  to manage/interact with Obsidian at all, so it's now just idle infrastructure (harmless, not
  worth ripping out).
- **Intake capture layer + Business OS services — DONE 2026-07-01.** Full write-up:
  `docs/roadmap-full-os.md`. Summary: built the real `platform/intake` service (was a stub —
  README + schema only, no code) with `POST /intake/lead` and `POST /intake/transcript`,
  bearer-token-gated (`INTAKE_SHARED_SECRET`), both normalizing input → vault note → pinging
  the agent to extract action items and draft (never send) follow-ups under
  `Inbox/approvals/`. Verified end-to-end with test data (then cleaned up — was fabricated
  content, not real). Also ported EspoCRM/Metabase/n8n from the separate, never-deployed
  `~/business-os` project into *this* VPS's existing Postgres+Tailscale+Caddy stack (avoids
  needing the `HCLOUD_TOKEN`/Cloudflare-tunnel setup that project was blocked on). Each new
  service gets its own dedicated `tailscale serve --https=PORT` (8443 CRM, 8444 BI, 8445
  flows) rather than a Caddy subpath — these apps assume domain root, same lesson as the
  Nextcloud `/files` bug. Verified: all three reachable over Tailscale, all three refused on
  the public IP (`nc` test). Cal.com deliberately deferred — heaviest of the four, wanted the
  simpler three proven first. **Needs Jake:** one-time login setup on Metabase (`:8444`) and
  n8n (`:8445`) — no way to create those accounts without him. Everything else needed to reach
  "full enterprise OS" (Google/Meta Ads API tracking, jacobdart.com lead capture, Gmail/Calendar
  MCP for real calendar writes, Otter/tldv re-auth) is credential-blocked on Jake's side —
  itemized with exact next steps in `docs/roadmap-full-os.md`.
- MCP connectors (Gmail/Calendar via Nango) — credential-blocked, see roadmap doc
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

**Next real work item**: See `docs/roadmap-full-os.md` for the full "enterprise OS" plan and
exact blockers. Short version: chat + vault second brain (done), intake capture + auto-draft
loop (done), CRM/BI/workflow apps deployed (done, need Jake's one-time logins on Metabase/n8n).
Everything past that — ad campaign tracking, jacobdart.com lead capture, real calendar writes,
Otter/tldv re-auth — is blocked on Jake providing credentials/OAuth consent/one code change in
a different repo; itemized with next steps in the roadmap doc. **Open decision, not yet
resolved**: whether to keep Tailscale-only access for everything, or move to a hybrid model
(Tailscale for SSH/admin, public HTTPS+auth for user-facing apps) — raised by Jake, relevant
now that jacobdart.com needs to reach the intake endpoint; see roadmap doc §1 for the Funnel
option.

**Known follow-up (not blocking)**: no persistent fix exists yet for the Mac's Mullvad
DNS-clobbering or firewall-blocking-CGNAT issues (see Phase 2 section above) — unlike Fedora's
`ts-mullvad-reconcile.timer`, there's no macOS daemon reasserting Tailscale's DNS/firewall
exceptions after a Mullvad reconnect. Worth building if this keeps recurring; needs Jake's
interactive `sudo` to inspect `pfctl` rules first.
