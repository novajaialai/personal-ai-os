#!/usr/bin/env bash
# Switch from NordVPN → Mullvad with Tailscale split tunneling.
# Run as: bash switch-to-mullvad.sh <mullvad-account-number>
# Get your account number at: https://mullvad.net/account

set -euo pipefail

ACCOUNT="${1:-}"
if [[ -z "$ACCOUNT" ]]; then
  echo "Usage: $0 <mullvad-account-number>"
  echo "Get one at https://mullvad.net/account (create account → no email needed)"
  exit 1
fi

echo "=== Installing Mullvad VPN ==="
rpm --import https://repository.mullvad.net/rpm/mullvad-keyring.asc
dnf config-manager --add-repo https://repository.mullvad.net/rpm/stable/mullvad.repo
dnf install -y mullvad-vpn mullvad-browser 2>/dev/null || dnf install -y mullvad-vpn

echo "=== Connecting account ==="
mullvad account login "$ACCOUNT"

echo "=== Configuring: split tunneling for Tailscale ==="
mullvad split-tunnel set state on
# Exclude the Tailscale daemon — its traffic bypasses Mullvad entirely
TAILSCALED=$(which tailscaled 2>/dev/null || echo /usr/sbin/tailscaled)
mullvad split-tunnel app add "$TAILSCALED"
echo "  Split tunnel: tailscaled excluded from Mullvad"

echo "=== Configuring: kill switch + DNS ==="
mullvad lockdown-mode set state on    # block traffic if VPN drops (equiv to Nord kill switch)
mullvad dns set default               # use Mullvad's DNS

echo "=== Configuring: auto-connect on boot ==="
mullvad auto-connect set state on

echo "=== Connecting to nearest server ==="
mullvad relay set tunnel-protocol any
mullvad connect
sleep 5
mullvad status

echo "=== Stopping and disabling NordVPN ==="
systemctl stop nordvpnd 2>/dev/null || true
systemctl disable nordvpnd 2>/dev/null || true
# nordvpn is left installed in case you want to roll back; to remove:
# dnf remove -y nordvpn

echo "=== Verifying Tailscale still works ==="
sleep 3
if tailscale ping 100.69.188.122 --timeout 10s 2>&1 | grep -q "pong\|via"; then
  echo "✓ Tailscale is working through Mullvad split tunnel"
else
  tailscale status 2>&1 | grep aios
  echo "(If rx>0 above, Tailscale is working. DERP relay is fine with Mullvad.)"
fi

echo ""
echo "Done. Mullvad is running with Tailscale excluded from the tunnel."
echo "NordVPN is stopped but not removed (roll back: systemctl start nordvpnd)."
echo "To verify: https://mullvad.net/check"
