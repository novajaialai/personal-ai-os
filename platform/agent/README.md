# Agent service (the brain)

Headless Claude Agent SDK service. One agent, multiple modes (second brain, EA,
tutor, trainer, coach) selected by system prompt + skill pack + thread namespace.

## Responsibilities
- Expose a chat/voice endpoint on the tailnet (Caddy proxies to it).
- Read/write the Obsidian vault (`/vault`) — long-term memory.
- Persist conversation threads to SQLite (`/state`) — "pick up where I left off".
- Call tools via MCP-native connectors first, then self-hosted Nango.

## Build
Add the Agent SDK runtime here (Dockerfile + entrypoint). Keep secrets in env,
never in the image. Tokens persist to the encrypted secrets store.

> Stub — implemented in Phase 3.
