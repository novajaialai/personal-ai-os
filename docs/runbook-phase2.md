# Personal AI OS — Phase 2 Runbook (v1)

**Goal:** stand up the first real services — **Nextcloud + the Obsidian vault** — synced to all
four devices over the tailnet, with a write discipline that won't corrupt the vault, and a
**deliberate conflict test** to prove it. After this phase you have "my files everywhere" plus a
vault the agent will later read and write.

**Prerequisite:** Phase 1 complete — box hardened, tailnet-only, `TAILSCALE_IP` in `.env`, SOPS
secrets, tested restic backups.

---

## Design decision (refines the brief)

The brief said "agent writes the vault via git." Designing this step, that's the wrong transport —
git and Nextcloud both writing the same folder is the conflict trap we're avoiding. Corrected design:

- **Nextcloud = the device-sync transport** for the vault and all files. Single coordinator.
- **The agent writes through WebDAV** (Nextcloud's API), not raw disk. No reindex problems, and
  Nextcloud's own conflict handling applies uniformly to agent and human edits.
- **git = periodic history/rollback snapshot** of the vault on the server (hourly commit), for
  "undo" and audit — **not** the sync path. `.git` is never synced to devices.

This is the single-writer-coordinator pattern: everything funnels through Nextcloud; git is a time
machine behind it.

---

## 2.1 Data layout on the box
```bash
# on the box, as aios
sudo mkdir -p /srv/aios/{nextcloud,vault,db}
sudo chown -R aios:aios /srv/aios
# vault is also a git repo for history (NOT synced to devices)
git -C /srv/aios/vault init -q
mkdir -p /srv/aios/vault/{Inbox/transcripts,CONTEXT,Personal,Business,Projects}
printf '.obsidian/workspace*\n.trash/\n' > /srv/aios/vault/.gitignore
git -C /srv/aios/vault add -A && git -C /srv/aios/vault commit -qm "Init vault"
```

## 2.2 Secrets for Nextcloud
Add to the encrypted `.env` (then re-encrypt with SOPS as in Phase 1):
```bash
NEXTCLOUD_ADMIN_USER=jake
NEXTCLOUD_ADMIN_PASSWORD=<openssl rand -base64 24>
NEXTCLOUD_TRUSTED_DOMAINS=aios-jake.<your-tailnet>.ts.net
POSTGRES_HOST=db
```
Confirm `platform/docker-compose.yml` passes these through to the `nextcloud` service `env_file`.

## 2.3 TLS on the tailnet (real cert, no warnings)
Use Tailscale's Let's Encrypt cert for the MagicDNS name, hand it to Caddy:
```bash
# on the box — enable HTTPS in the Tailscale admin first (MagicDNS + HTTPS)
sudo tailscale cert aios-jake.<your-tailnet>.ts.net
# writes aios-jake.<tailnet>.ts.net.crt / .key into the working dir
sudo mkdir -p /srv/aios/caddy/certs
sudo mv aios-jake.*.crt aios-jake.*.key /srv/aios/caddy/certs/
```
Point the Caddyfile site block at the cert:
```caddyfile
{$AIOS_HOSTNAME} {
	tls /certs/aios-jake.<tailnet>.ts.net.crt /certs/aios-jake.<tailnet>.ts.net.key
	@nextcloud path /files/*
	handle @nextcloud { reverse_proxy nextcloud:80 }
	handle { reverse_proxy agent:3000 }
}
```
Mount `/srv/aios/caddy/certs` into the caddy container as `/certs`.

## 2.4 Bring up the data services
```bash
cd ~/personal-ai-os
sops --decrypt secrets/.env.enc > .env          # plaintext only on the box, briefly
docker compose -f platform/docker-compose.yml up -d db nextcloud caddy
docker compose -f platform/docker-compose.yml ps
```
Verify it's tailnet-only (the Phase 1 gotcha again):
```bash
# from your laptop — public must refuse, tailnet must work
nc -zv $(cd infra/terraform && terraform output -raw ipv4) 443   # refuse/timeout
curl -I https://aios-jake.<your-tailnet>.ts.net/files/           # 200/302 over tailnet
```

## 2.5 Configure Nextcloud + mount the vault
First load completes the install with the admin creds. Then make the vault a Nextcloud folder so
it syncs natively. Cleanest: add the vault as **External Storage (Local)** pointing at
`/srv/aios/vault`, scoped to your user:
```bash
docker compose exec --user www-data nextcloud php occ app:enable files_external
docker compose exec --user www-data nextcloud php occ files_external:create \
  "Vault" local null::null -c datadir=/srv/aios/vault
docker compose exec --user www-data nextcloud php occ files:scan --all
```
(Mount `/srv/aios/vault` into the nextcloud container at the same path.)

## 2.6 The agent's write path (WebDAV) — verify now
The agent will write here in Phase 4; prove the transport works today:
```bash
# create a note via WebDAV exactly as the agent will
curl -u jake:$NEXTCLOUD_ADMIN_PASSWORD -T - \
  "https://aios-jake.<tailnet>.ts.net/files/remote.php/dav/files/jake/Vault/Inbox/test.md" \
  <<< "# hello from webdav"
# confirm it appears and syncs; Nextcloud indexed it without a manual rescan
```

## 2.7 git history snapshot (hourly, server-side)
systemd timer commits vault history without touching devices:
```bash
# /etc/systemd/system/aios-vault-snapshot.service  (Type=oneshot)
ExecStart=/usr/bin/git -C /srv/aios/vault add -A
ExecStart=/usr/bin/git -C /srv/aios/vault commit -q -m "snapshot %i" --allow-empty
# paired .timer: OnCalendar=hourly
```
Enable it: `sudo systemctl enable --now aios-vault-snapshot.timer`.

## 2.8 Install device clients
- **Mac / Linux:** Nextcloud Desktop client → server `https://aios-jake.<tailnet>.ts.net`, sync the
  `Vault` folder locally. Open that folder as a vault in **Obsidian**. (Both machines must be on the
  tailnet — Tailscale running.)
- **Phone / tablet:** Nextcloud mobile app + Obsidian mobile pointed at the synced folder. On iOS,
  use the Nextcloud app's auto-upload/offline-sync for the vault folder.

## 2.9 Deliberate conflict test (the point of this phase)
1. **Two-device human edit:** on Mac and Linux, go offline, edit the *same* note differently,
   reconnect. Expect Nextcloud to keep both as a conflict copy — **no silent loss**. Resolve.
2. **Agent-vs-human concurrent:** write to a note via WebDAV (2.6) while editing the same note in
   Obsidian on a device. Confirm Nextcloud surfaces the conflict rather than overwriting.
3. **History rollback:** delete a note, then restore it from the git snapshot:
   `git -C /srv/aios/vault checkout HEAD~1 -- Path/To/note.md`.

**Pass = no edit is ever silently lost, and every conflict is recoverable** (Nextcloud conflict file
or git history).

## 2.10 Backups cover the vault
```bash
restic snapshots --tag aios
restic restore latest --target /tmp/r && ls /tmp/r/srv/aios/vault   # vault present
```

---

## Acceptance criteria (Phase 2 done)
- [ ] Nextcloud reachable over the tailnet with a valid TLS cert; **public IP refuses 443**.
- [ ] Vault visible in Nextcloud and syncing to Mac, Linux, phone, tablet.
- [ ] Obsidian opens the synced vault on at least Mac + one mobile device.
- [ ] Agent WebDAV write lands and indexes without a manual rescan.
- [ ] Hourly git snapshot timer active; rollback tested.
- [ ] Conflict test passed — no silent data loss.
- [ ] restic restore shows the vault.

## Next (Phase 3 preview)
Deploy the headless Claude agent with read/write to the vault **via WebDAV** + a SQLite session
store, reachable over the tailnet, text-first. Prove "pick up where I left off" across two devices.
That's the next runbook.
