# Personal AI OS

A deployable, sovereign personal-and-business AI operating system: a persistent
Claude agent (second brain, executive assistant, tutor, trainer, coach) reachable
from every device, with voice, an Obsidian second brain, and a capture layer that
turns meetings and voice notes into actions.

This repo **is the product**. It deploys onto a fresh VPS in minutes and is
customized by conversation (the onboarding interview skill), not config editing.

## The core split: platform vs tenant
- **platform/** + **infra/** + **skills/** — generic, identical on every deploy.
- **templates/** — per-tenant config (context, secrets, connectors) injected at provision.
- You are **tenant zero**: the first deployment of the generic template.

## Deploy in 3 steps
```bash
# 1. Provision a hardened, tailnet-only VPS (Docker + Tailscale)
cd infra/terraform && terraform apply

# 2. Bring up the platform with per-tenant secrets
./scripts/bootstrap.sh

# 3. Personalize by conversation (writes context files + starter workflows)
./scripts/customize.sh
```

## Two snapshot layers
- **Golden image** (Packer-built from this repo) → minutes-fast spin-up.
- **This repo** → source of truth that regenerates the image. The image is a cache; the repo is the truth.

See `docs/architecture.md` for the full design and `docs/runbook-phase0-1.md` to start building.
