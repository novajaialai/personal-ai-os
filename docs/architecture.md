# Architecture

See `personal-ai-os_Brief_v3.md` (the planning brief) for the full reasoning.
Quick map:

- **Devices** (phone/tablet/Mac/Linux) → **Tailscale mesh** → **Caddy** → services.
- **Agent core** (Claude Agent SDK): the brain, one agent / many modes.
- **Memory**: Obsidian vault (long-term, git-managed) + SQLite session store (mid-term).
- **Capture layer**: one intake → normalized transcript → agent extracts actions.
- **Auth**: MCP-native first → self-hosted Nango → hand-roll. No Composio in the hot path.
- **Secrets**: SOPS+age token vault; tailnet-only; backups encrypted.
- **Productization**: platform (generic) vs tenant config (injected); customer-zero-is-you;
  golden image for speed, this repo as source of truth.
