# Agent OS front door — Cloudflare Tunnel + Access

Agent OS ("Agentic OS", Julian Goldie's Next.js Mission Control) runs on this box as the
central agent dashboard and is exposed to the public internet at **https://agentos.jacobdart.com**,
gated by Cloudflare Access. Deployed 2026-07-05. Integrated alongside the `platform/` stack
(nothing was overwritten).

## Topology

```
phone / laptop (anywhere)
    |  https://agentos.jacobdart.com
    v
Cloudflare edge  --(Access: one-time PIN, allow only yakobdart@gmail.com)-->
    |  outbound-only QUIC tunnel (no inbound ports opened on the box)
    v
cloudflared.service  -->  http://127.0.0.1:3737  (agent-os.service, Next.js)
    |
    +-- shells out to local hermes / claude CLIs, reads ~/.hermes, ~/.agentic-os
```

Agent OS has NO built-in auth and its API routes run shell commands (RCE-equivalent).
Cloudflare Access IS the auth layer. Two hard rules:
1. The app binds 127.0.0.1 ONLY (never 0.0.0.0). Verified: off-box hit of :3737 is refused.
2. The Access policy must be enforcing BEFORE the tunnel DNS route is live.

## Components (all boot-persistent systemd)

- **agent-os.service** — `PORT=3737 npm start` in `~/agent-os/source`, binds 127.0.0.1:3737.
- **cloudflared.service** — `cloudflared --config /etc/cloudflared/config.yml tunnel run`.
  Tunnel name `agent-os`, id `9704100e-6381-4ae1-a5c5-603dcac4d270`. Locally-managed:
  `cert.pem` + `<id>.json` credentials live in `/home/aios/.cloudflared/` (NEVER commit these).
- **Cloudflare zone** jacobdart.com (`bb7a347b8a781c243b26b7c448295d86`), Free plan,
  acct yakobdart@gmail.com (`e336a3a5474f2838987ea69e05b4ef67`). `agentos` = proxied CNAME
  → the tunnel. The apex + www stay DNS-only (GitHub Pages site, untouched).
- **Cloudflare Access** self-hosted app "agentos" (Public DNS destination agentos.jacobdart.com),
  policy "Only Jake" = Allow / Include Emails = yakobdart@gmail.com, 24h session.
  Zero Trust Free plan. Team domain: `patient-scene-ed10.cloudflareaccess.com`.
  Login method: one-time PIN emailed to the allowed address (no IdP configured).

Files here: `agent-os.service`, `cloudflared.service`, `cloudflared-config.example.yml`
(the live config, minus the secret credentials json it references).

## Reproduce on a fresh box

```
# prereqs: Node 22, hermes + claude CLIs authed, ~/.agentic-os/config.json, swap added
rsync agent-os/ to ~/agent-os ; cd source ; npm ci ; npm run build
install agent-os.service ; systemctl enable --now agent-os
cloudflared tunnel login                       # authorize the zone in browser (one time)
cloudflared tunnel create agent-os
cp cloudflared-config.example.yml ~/.cloudflared/config.yml   # fix tunnel id + creds path
# >>> create the Access app + policy FIRST, confirm it is enforcing <<<
cloudflared tunnel route dns agent-os agentos.jacobdart.com
sudo cloudflared --config ~/.cloudflared/config.yml service install
systemctl enable --now cloudflared
```

## Verify (must all pass before trusting it)

```
curl -s -o/dev/null -w "%{http_code}\n" http://127.0.0.1:3737/api/vitals            # 200 (app up)
curl -s -o/dev/null -w "%{http_code}\n" --connect-timeout 6 http://<box-ip>:3737/    # 000/refused (not exposed)
curl -s -o/dev/null -w "%{http_code}\n" --max-redirs 0 https://agentos.jacobdart.com/api/vitals  # 302 -> Access login, NOT 200
```

## Add / remove a person (Cloudflare Access)

There is NO separate account to create. Identity = the person's email + a one-time PIN.
Dashboard → Zero Trust → Access controls → Applications → agentos → policy "Only Jake"
→ Include Emails: add their address (or "Emails ending in @domain"). Remove = delete the email.

**WARNING:** Agent OS has no per-user isolation. Anyone allowed gets FULL control of this box
(run shell, spend API money, read Twenty CRM / Nextcloud vault). Only add fully-trusted people.
For untrusted/limited sharing, give them a separate instance, not a login here.

## Teardown (fully reversible, additive)

```
systemctl disable --now cloudflared agent-os
cloudflared tunnel delete agent-os
# delete the Access app + policy in the dashboard; (optionally) point NS back to Hostinger
```
