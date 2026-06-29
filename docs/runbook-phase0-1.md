# Personal AI OS — Phase 0 & 1 Runbook (v1)

**Goal of these two phases:** go from an empty repo to a **hardened, tailnet-only VPS with a real secrets vault and tested encrypted backups** — the foundation every later phase sits on. No agent, no Nextcloud yet. Just a box you'd trust with your whole life, built as reproducible code.

Run everything from your Mac/Linux laptop unless a step says "on the box."

---

## Prerequisites (accounts + local tools)

| Need | Why | Get it |
|---|---|---|
| Hetzner Cloud account + **API token** | Provision the VPS | console.hetzner.cloud → Security → API Tokens (Read & Write) |
| Tailscale account | Private mesh; no public exposure | tailscale.com, free tier |
| Private git remote | Repo = source of truth | GitHub private repo or self-hosted Gitea |
| Hetzner **Storage Box** (or Backblaze B2) | Off-box encrypted backups | Hetzner Robot, ~€3.20/mo for 1TB |

Local CLI tools:
```bash
# macOS (brew); Linux use your package manager
brew install terraform tailscale sops age restic
ssh-keygen -t ed25519 -C "aios" -f ~/.ssh/aios   # dedicated key for this project
```

---

## Phase 0 — Template scaffold + stack inventory

### 0.1 Put the skeleton under version control
```bash
cd personal-ai-os
git init -b main
git add .
git commit -m "Scaffold Personal AI OS template"
git remote add origin git@github.com:<you>/personal-ai-os.git   # PRIVATE repo
git push -u origin main
```
Confirm `.gitignore` is doing its job — **no `.env`, no `secrets/`, no `tfstate` should ever appear**:
```bash
git status --ignored | grep -E '\.env|secrets/|tfstate'   # should list them as IGNORED
```

### 0.2 Stack inventory (the stated goal of the "My stack" project)
Document what's already on your Mac/Linux laptop so we know what to migrate vs rebuild. Dump the easy stuff automatically:
```bash
mkdir -p docs/stack-inventory && cd docs/stack-inventory
brew leaves > brew-packages.txt 2>/dev/null || true       # macOS
dpkg --get-selections > apt-packages.txt 2>/dev/null || true  # Linux
pip list > pip.txt 2>/dev/null; npm ls -g --depth=0 > npm-global.txt 2>/dev/null
crontab -l > crontab.txt 2>/dev/null || true
ls -la ~ > home-listing.txt
cd ../..
```
Then hand-write `docs/stack-inventory/README.md` covering what tooling won't show:
- **Obsidian vault** — where it lives, folder structure, plugins, current sync method.
- **Connectors already in use** — Gmail, Calendar, Otter, etc., and how they auth today.
- **Scripts/automations** you rely on and want ported.
- **What stays on the laptop** vs what moves to the VPS.

### 0.3 Lock the platform-vs-tenant boundary
One short doc, `docs/boundaries.md`: list every component as **platform (generic)** or **tenant (injected)**. This is the discipline that keeps the product templatizable. If you can't decide where something goes, it's tenant config until proven otherwise.

### 0.4 Drop in the skills
Place the actual skill folders in `skills/` — at minimum the **onboarding-interview** (your customization engine) and **prime**. Commit.

**Phase 0 done when:** repo is pushed, secrets are provably ignored, inventory exists, boundary doc exists, skills are in `skills/`.

---

## Phase 1 — Foundation + secrets

### 1.1 Keys: SSH + age
```bash
# SSH public key → paste into infra/cloud-init.yaml (replace REPLACE_WITH_YOUR_PUBLIC_KEY)
cat ~/.ssh/aios.pub

# age keypair for SOPS — the master key that encrypts all secrets
age-keygen -o ~/.config/aios/age.key      # prints the public recipient (age1...)
```
Store the **age private key** somewhere safe and OFF the repo (password manager + a printed copy). Lose it and you lose every encrypted secret.

Add the SSH key to Hetzner and grab its ID:
```bash
export HCLOUD_TOKEN=<your-hetzner-token>
hcloud ssh-key create --name aios --public-key-from-file ~/.ssh/aios.pub
hcloud ssh-key list   # note the ID for tfvars
```

### 1.2 Configure Terraform
Create `infra/terraform/terraform.tfvars` (gitignored — add `*.tfvars` to `.gitignore`):
```hcl
hcloud_token = "REDACTED"
tenant       = "jake"          # tenant zero
server_type  = "cpx41"         # 16GB — GUI headroom + build box
location     = "ash"           # US east; fsn1/nbg1 for EU
ssh_key_ids  = ["<id-from-above>"]
admin_cidrs  = ["<your-home-ip>/32"]   # tighten SSH to your IP
data_volume_gb = 50
```

### 1.3 Provision
```bash
cd infra/terraform
terraform init
terraform plan      # read it — confirm 1 server, 1 volume, 1 firewall
terraform apply
terraform output ipv4
```
cloud-init now installs Docker + Tailscale, creates the `aios` user, and locks the host firewall to default-deny inbound except on the tailnet. Give it ~2 minutes.

### 1.4 Join the tailnet and verify lockdown
On the box, authenticate Tailscale (cloud-init ran `tailscale up --ssh`; approve the node in the Tailscale admin console, or pre-auth with a key). Then from your laptop:
```bash
tailscale status                       # the box should appear
ssh aios@<tailscale-hostname>          # SSH over the tailnet — should work
tailscale ip -4 -peer <box>            # note the box's 100.x.y.z

# CRITICAL: confirm nothing is reachable on the PUBLIC IP
nc -zv $(terraform output -raw ipv4) 443    # should TIME OUT / refuse
nc -zv $(terraform output -raw ipv4) 80     # should TIME OUT / refuse
```
Public ports closed + tailnet SSH working = your access model is correct.

> **Docker-on-Linux gotcha (do not skip):** Docker writes its own iptables rules and **bypasses UFW** — a published port can be exposed to the internet even though `ufw status` looks locked. The fix in this stack: **bind every published port to the box's Tailscale IP, not 0.0.0.0.** `bootstrap.sh` captures it; set it before bringing up the stack in Phase 2:
> ```bash
> # on the box
> echo "TAILSCALE_IP=$(tailscale ip -4)" >> ~/personal-ai-os/.env
> ```
> and the compose `ports:` use `${TAILSCALE_IP}:443:443`. Verify later with `docker ps` + the same `nc` test against the public IP.

### 1.5 Secrets vault (SOPS + age)
On the laptop, point SOPS at your age recipient. Create `personal-ai-os/.sops.yaml`:
```yaml
creation_rules:
  - path_regex: \.env$
    age: "age1...your-public-recipient..."
```
Create and encrypt the real env (BYO keys for v1):
```bash
cp templates/.env.example .env
# fill ANTHROPIC_API_KEY, GROQ/DEEPGRAM/ELEVENLABS, RECALL, etc.
sops --encrypt --input-type dotenv --output-type dotenv .env > secrets/.env.enc
shred -u .env        # remove the plaintext; the encrypted copy is the artifact
git add .sops.yaml secrets/.env.enc && git commit -m "Add encrypted tenant secrets"
```
Decrypt-at-deploy on the box (only place plaintext briefly exists, in tmpfs):
```bash
sops --decrypt secrets/.env.enc > .env     # done inside bootstrap.sh
```
This keeps tokens on hardware you control and out of git in plaintext — the whole point versus a hosted broker.

### 1.6 Encrypted off-box backups (restic)
Back up the **vault + the token store + Nextcloud data** to a Storage Box, encrypted, automated, and — most importantly — **test-restored**.
```bash
# on the box, one-time
export RESTIC_REPOSITORY="sftp:u123456@u123456.your-storagebox.de:/backups/aios"
export RESTIC_PASSWORD="<strong-passphrase-stored-in-your-pw-manager>"
restic init
```
Nightly via systemd timer (`/etc/systemd/system/aios-backup.service` + `.timer`):
```bash
restic backup /srv/aios/vault /srv/aios/secrets /srv/aios/nextcloud \
  --tag aios --exclude-caches
restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune
```
**Then prove it:**
```bash
restic snapshots
restic restore latest --target /tmp/restore-test && ls -R /tmp/restore-test
```
A backup you haven't restored is a rumor.

### 1.7 Hardening verification checklist
- [ ] Password SSH disabled (`PasswordAuthentication no`), keys only.
- [ ] `ufw status` → default deny incoming, allow on `tailscale0`.
- [ ] Public IP `nc` test on 22/80/443 → all refused/timeout.
- [ ] `unattended-upgrades` active (`systemctl status unattended-upgrades`).
- [ ] age private key + restic passphrase stored off-box in your password manager.
- [ ] `terraform plan` shows **no drift** (infra matches code).

**Phase 1 done when:** every box above is checked, secrets round-trip through SOPS, and a restic restore succeeded.

---

## What this buys you

A reproducible, locked-down foundation that exists entirely as code — so **customer #2 is the same `terraform apply` with a different `tenant` and `.env`.** You've also dogfooded the deploy as tenant zero.

## Next (Phase 2 preview)
Stand up Nextcloud + the git-managed Obsidian vault as the first services on the box, bind them to the Tailscale IP per the gotcha above, sync to all four devices, and run a deliberate conflict test. I'll write that runbook when you're through Phase 1 — or sooner if you want to read ahead.
