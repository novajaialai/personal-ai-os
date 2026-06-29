# Hetzner Cloud provisioning for one Personal AI OS instance (one VPS per tenant).
# Provider-agnostic platform runs in Docker on top; swap this file for another host.

terraform {
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

resource "hcloud_server" "aios" {
  name        = "aios-${var.tenant}"
  server_type = var.server_type # cpx41 (tenant-zero) | cpx31 (light customer)
  image       = "ubuntu-24.04"
  location    = var.location
  ssh_keys    = var.ssh_key_ids
  user_data   = file("${path.module}/../cloud-init.yaml")

  labels = {
    product = "personal-ai-os"
    tenant  = var.tenant
  }
}

resource "hcloud_volume" "data" {
  name      = "aios-${var.tenant}-data"
  size      = var.data_volume_gb
  server_id = hcloud_server.aios.id
  automount = true
  format    = "ext4"
}

# Firewall: deny everything inbound from the public internet.
# All access is via the Tailscale tailnet, not exposed ports.
resource "hcloud_firewall" "lockdown" {
  name = "aios-${var.tenant}-fw"

  # SSH only as a break-glass fallback; prefer Tailscale SSH.
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = var.admin_cidrs
  }
}

resource "hcloud_firewall_attachment" "fw" {
  firewall_id = hcloud_firewall.lockdown.id
  server_ids  = [hcloud_server.aios.id]
}
