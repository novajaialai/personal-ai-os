# Full personal + business OS — architecture & roadmap

**Date:** 2026-07-01
**Trigger:** Jake wants chat + full dashboards + ad-campaign tracking (Google/Meta) + website
lead capture (jacobdart.com) + calendar automation + Otter/tldv → action items, "as close to
an enterprise OS as possible" for running both personal life and the business.

## The big finding

Most of this already existed as a **separate, undeployed project**: `~/business-os`
(EspoCRM + Metabase + n8n + Cal.com, designed for a second Hetzner VPS behind Cloudflare
Tunnel, blocked on an `HCLOUD_TOKEN` Jake never provided). Standing up a second VPS with a
different exposure model (Cloudflare-fronted vs. this box's Tailscale-only model) would have
meant maintaining two separate security postures for no real benefit. **Instead: the proven
service definitions from `business-os` were ported into this VPS's existing stack**, reusing
the already-provisioned Postgres instance and the already-working Tailscale+Caddy setup. Zero
new tokens needed for the infra piece.

## What's live right now (2026-07-01)

| Service | URL | Purpose | Status |
|---|---|---|---|
| Agent chat | `https://aios-jake-1.tail828365.ts.net/` | Second brain, now with real vault tools (list/search/read/write/append notes) | ✅ Live, verified |
| Intake API | `.../intake/lead`, `.../intake/transcript` | Webhook capture → vault → agent auto-drafts follow-ups/action items | ✅ Live, verified end-to-end |
| Twenty CRM | `https://aios-jake-1.tail828365.ts.net:8443/` | CRM — contacts, leads, deals pipeline | ✅ Live, **needs one-time setup**: visit once, create your own account (swapped from EspoCRM 2026-07-01 — Twenty is better-designed/more modern; EspoCRM removed) |
| Metabase | `https://aios-jake-1.tail828365.ts.net:8444/` | BI / dashboards — "beautiful data rendered" | ✅ Live, **needs one-time setup**: visit once, create your own admin login |
| n8n | `https://aios-jake-1.tail828365.ts.net:8445/` | Workflow automation spine (ad tracking, lead routing, anything cross-system) | ✅ Live, **needs one-time setup**: visit once, create your own owner account. No n8n.io account needed — self-hosted, fully free (Sustainable Use License), telemetry disabled. |
| Nextcloud | `https://aios-jake-1.tail828365.ts.net/files` | Files (vault is here too, but you don't need to touch it — chat is the interface) | ✅ Already running |
| Daily briefing | systemd timer, 07:03 UTC | Agent proactively reviews Inbox/leads, Inbox/transcripts, Inbox/approvals, action-items.md and writes a digest — **no one has to ask**. First piece of actual Jarvis-style "acts on its own" behavior, vs. only reacting to chat/webhooks. | ✅ Live, verified (`infra/systemd/aios-daily-briefing.*`, `scripts/aios-daily-briefing.sh`) |

Each new service is exposed on its own dedicated Tailscale HTTPS port (`8443`/`8444`/`8445`)
rather than a Caddy subpath — apps like EspoCRM/Metabase/n8n assume they own their domain root
and don't tolerate being reverse-proxied under a prefix cleanly (see the Nextcloud `/files`
lesson in `HANDOFF.md`, 2026-07-01). Verified: none of these ports are reachable on the VPS's
public IP — Tailscale-only, per guardrail #1.

## What's built but not yet wired to real data

**Intake → agent → draft loop** (verified end-to-end with test data, then cleaned up):
1. `POST /intake/lead` — website lead capture (name, email, message, intent)
2. `POST /intake/transcript` — meeting transcript capture (Otter/tldv/Recall-shaped)
3. Both write a normalized note to the vault, then ping the agent to process it
4. The agent reads the new note, extracts action items (appended to `Inbox/action-items.md`),
   and drafts any follow-up email/call as a review-only note under `Inbox/approvals/` —
   **nothing sends automatically**, matching the approvals-gate design in
   `docs/runbook-phase4.md` guardrail #6

Both endpoints require `Authorization: Bearer <INTAKE_SHARED_SECRET>` (generated, in `.env` on
the VPS) — this matters once anything public-facing calls them (see jacobdart.com below).

## What's next, and exactly what's blocking each piece

None of these are things I can complete myself — each needs either Jake's credentials, a
one-time OAuth consent in a browser, or a code change to a repo outside `personal-ai-os`.
Everything above is ready and waiting for these:

### 1. jacobdart.com → lead capture
**Blocker:** need to add a `fetch()` call to the contact/call-request form in the
`novajaialai/jmai-site` repo (GitHub Pages — static site, no server-side code), posting to
`POST https://aios-jake-1.tail828365.ts.net/intake/lead`.
**Bigger blocker:** GitHub Pages is public, but this VPS is Tailscale-only — a visitor's
browser isn't on the tailnet, so it physically cannot reach that URL as-is. Two ways through:
- **Tailscale Funnel** on just this one path (`tailscale funnel --set-path /intake/lead`) —
  exposes *only* that endpoint to the public internet, everything else on the box stays
  private. This is a real security-posture change (guardrail #1 says "nothing exposed to the
  public internet") — deliberately not flipped on without you confirming. Say the word and
  it's a 2-minute change plus the site-side fetch() call.
- Or: put the form behind a tiny public serverless function (Cloudflare Worker) that forwards
  to the VPS over the tailnet via Cloudflare's own private networking — more moving parts, more
  "proper" for a growing business, not needed at this stage.
**Recommendation:** Funnel, scoped to that one path only. Ask when ready.

### 2. Google Ads / Meta Ads campaign tracking
**Blocker:** need your ad account API credentials (OAuth for both platforms — Google Ads API
requires a developer token + OAuth client; Meta Marketing API requires a Meta for Developers
app + long-lived token). Neither can be created without you in the loop (business verification,
2FA, etc.).
**What's ready:** n8n is live and is exactly the tool for this — once credentials exist, an n8n
workflow polls both platforms' reporting APIs on a schedule, normalizes spend/conversions/leads,
writes to Postgres, and Metabase dashboards render it. I can build the actual n8n workflow JSON
and Metabase dashboard the moment credentials land — that part is pure config, no blockers once
unblocked.

### 3. Calendar automation (call requests → calendar)
**Blocker:** Google Calendar (or Cal.com) OAuth — same MCP-native-first pattern already
documented in `docs/runbook-phase4.md` §4.1. Cal.com itself wasn't deployed in this pass
(it's the heaviest of the four business-os services — many required env vars, SMTP config —
deliberately deferred to avoid shipping something broken; EspoCRM/Metabase/n8n were higher
leverage and are proven-simple to deploy).
**What's ready:** the agent already drafts "proposed call logistics" in its approval notes
(verified in testing) — it just can't write directly to a real calendar yet. Once
Gmail/Calendar MCP is authorized (one browser OAuth flow), wire `calendar.propose` as a 6th
agent tool alongside the 5 vault tools already built.

### 4. Otter.ai / tl;dv → real transcripts (not just the webhook receiver)
**Blocker:** Otter MCP connection needs to be re-verified live (brief.md says "already
connected" from earlier exploration, unconfirmed today) — tl;dv MCP tools exist in this
session's toolset but that's *my* session's connection, not the VPS agent's; the VPS agent
needs its own credentials wired via Nango (self-hosted OAuth broker, already running, currently
idle) or a direct webhook from Otter/tldv's own integration settings pointed at
`POST /intake/transcript`.
**What's ready:** the receiving end is fully built and tested. This is the "prove the loop on
Otter MCP first" acceptance demo from `runbook-phase4.md` §4.4 — lowest-lift path once
re-authorized.

## Immediate next steps, in order of leverage

1. **You:** visit Metabase (`:8444`) and n8n (`:8445`) once each, create your own login —
   2 minutes, unblocks dashboard-building and workflow-building respectively
2. **You:** confirm whether to enable Tailscale Funnel for `/intake/lead` (see #1 above) — once
   confirmed, I wire the jacobdart.com form and it's a live lead pipeline same day
3. **You:** when ready for ad tracking, get Google Ads + Meta Marketing API access started
   (developer token / app review can take a few days on Meta's side — worth starting early even
   before the n8n workflow is built)
4. **Me, once #2 is confirmed:** wire the jacobdart.com contact form
5. **Me, once #3 lands:** build the n8n ad-tracking workflow + first Metabase dashboard
6. **Later:** Cal.com deploy (once the simpler 3 services are proven stable for a few days) or
   Gmail/Calendar MCP auth, whichever Jake wants to unblock first — calendar automation is
   probably higher leverage day-to-day than a 4th dashboard app
