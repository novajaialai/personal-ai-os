#!/usr/bin/env bash
# Personalize a deployment BY CONVERSATION.
# Runs the onboarding interview skill against the live agent, which interviews
# the tenant and writes their context files + starter workflows into the vault.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VAULT_PATH=$(grep '^VAULT_PATH=' "$ROOT/.env" | cut -d= -f2)

echo "==> Seeding blank context templates into the vault"
mkdir -p "$VAULT_PATH/CONTEXT"
cp -n "$ROOT"/templates/context/*.md "$VAULT_PATH/CONTEXT/"

cat <<'MSG'

==> Now run the onboarding interview:
    Open the agent (chat or voice) and start the 'onboarding-interview' skill.
    It will ask: who are you, what does the business do, top headaches, which tools.
    It writes answers into CONTEXT/ and drafts starter workflows.

    This is the customization step — same image for every tenant, personalized by talking.
MSG
