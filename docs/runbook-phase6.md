# Personal AI OS — Phase 6 Runbook (v1)

**Goal:** turn your working tenant-zero box into a **product you can deploy for a customer in
minutes** — a golden image, idempotent deploy scripts, parameterized provisioning, and a
**clean-room dry run** on a throwaway VPS as a fake customer that proves the template stands up with
**zero tenant-zero data leakage.**

**Prerequisite:** Phases 1–5 working on tenant zero (your box).

---

## Design notes

- **Customer-zero-is-you paid off:** you built the template the deployable way, so this phase is
  packaging and proof, not a rewrite.
- **The repo is the source of truth; the image is a cache.** Everything the image contains must be
  rebuildable from the repo via Packer.
- **Isolation is the product.** One VPS per customer, per-tenant secrets, per-tenant backups. Nothing
  shared between tenants — ever.

---

## 6.1 Freeze the platform/tenant boundary (audit)
Before baking anything, prove no tenant data is in the generic layers:
```bash
# nothing tenant-specific in platform/, infra/, skills/
grep -rInE 'jake|aios-jake|<your-tailnet>|real-secret' platform/ infra/ skills/   # expect no hits
```
All tenant-specific values must live only in `templates/` + injected `.env` + `tenant.yaml`.

## 6.2 Packer golden image
Build a Hetzner snapshot from the repo (OS + Docker + pre-pulled platform images + cloud-init):
```
infra/packer/aios.pkr.hcl     # source = hcloud ubuntu-24.04; provisioners install docker,
                              # tailscale, age/sops/restic, and `docker compose pull` the stack
```
```bash
cd infra/packer && packer build aios.pkr.hcl   # outputs a snapshot ID
```
Point Terraform at it: `image = var.golden_snapshot_id`. Spin-up drops from ~minutes-of-setup to
boot-time, because images are already pulled.

## 6.3 Idempotent bootstrap + customize
- `scripts/bootstrap.sh`: safe to re-run. Generates per-tenant secrets if absent, inits the vault,
  captures `TAILSCALE_IP`, `docker compose up -d`. No hard-coded tenant values.
- `scripts/customize.sh`: runs the **onboarding-interview** skill against the live agent → writes the
  customer's `CONTEXT/` files + starter workflows + which connectors to enable. Customization by
  conversation, not file editing.

## 6.4 Parameterized provisioning
One tenant = a tfvars file + an env:
```hcl
# infra/terraform/tenants/acme.tfvars
tenant       = "acme"
server_type  = "cpx31"          # customer floor
golden_snapshot_id = "…"
```
```bash
terraform apply -var-file=tenants/acme.tfvars
```
New customer = `terraform apply` (new tenant) → `bootstrap.sh` → `customize.sh` → customer connects
their tools via the MCP-first flow.

## 6.5 Clean-room dry run (the proof)
Deploy as a fake customer on a **throwaway** VPS, with none of your data:
1. `terraform apply -var-file=tenants/acme.tfvars` (fresh box, fresh tenant).
2. `bootstrap.sh` → stack up; confirm public-IP `nc` refuse test passes.
3. `customize.sh` → run the onboarding interview *as if you were Acme* (fake answers).
4. Connect one test connector; push a sample transcript through `/intake`; confirm the
   draft-email + propose-event + approvals loop works.
5. **Verify zero leakage:** no `jake`/tenant-zero secrets, vault content, or tokens anywhere on the
   Acme box.
6. `terraform destroy -var-file=tenants/acme.tfvars` → clean teardown.

Pass = a stranger's box went zero → interviewed → capturing → destroyed, with no trace of you.

## 6.6 Versioning + upgrades
- Tag the template: `git tag v1.0.0`. Customers pin a version.
- Rebuild the golden image per tagged release.
- Upgrade path: `docker compose pull && up -d` on a tenant to roll platform images forward; document
  any migration steps per release in `docs/CHANGELOG.md`.

## 6.7 Per-tenant isolation (non-negotiable)
- Each tenant: its **own age key**, its **own restic repo**, its **own Nango DB / tokens**. Never
  shared, never cross-mounted.
- BYO API keys per tenant (v1). If you later offer provision-and-meter, that's a separate managed
  billing path — don't retrofit shared keys into this design.

## 6.8 Customer deploy doc
Write `docs/deploy-customer.md`: the 3-command deploy + the interview, plus a pre-flight checklist
(Hetzner token, customer's Tailscale, their API keys). This is what you hand a customer or run for them.

---

## Acceptance criteria (Phase 6 done)
- [ ] Boundary audit clean — no tenant data in platform/infra/skills.
- [ ] Packer builds a golden image reproducibly from the repo.
- [ ] `bootstrap.sh` + `customize.sh` are idempotent and tenant-parameterized.
- [ ] Clean-room dry run: throwaway VPS → interviewed → capture loop works → destroyed.
- [ ] Zero tenant-zero leakage verified on the throwaway box.
- [ ] Template tagged (`v1.0.0`); upgrade path documented.
- [ ] Per-tenant secrets/backups/tokens fully isolated.

## Done
Six phases complete: a sovereign personal AI OS running for you, and a template that deploys the same
thing for customers in minutes — one VPS each, customized by conversation. That's the product.
