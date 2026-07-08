# Jacob OS — Local Websites & Internal Tools Implementation Plan

**Date:** 2026-06-09  
**Principle:** Volume compounds skill (100 pots). Ship fast iterations, learn from real use.  
**Goal:** Two polished websites + internal tooling hub that compounds over time.  
**Aesthetic:** Linear + n8n inspired — warm dark grays (#1e1e24, #16161a), Hermes purple accents (#8b5cf6), glassmorphism cards, color-coded badges (green=active, amber=pending, coral=alert, teal=success), left accent strips on nodes/cards, proper spacing (16/24/32/48px scale), SF-style typography.

---

## Strategic Opinion: Why This Approach Wins

**Local Internal Hub First (Priority #1)**  
- Everything we’ve built (memory.db, playbook, tool-catalog, prospect-audit skill, reflection, contacts, goals) lives here.  
- A beautiful localhost web app becomes the **daily driver** for Jacob OS — view playbook, manage prospects, launch skills, see reflection outputs.  
- n8n-style UX makes the "skills as nodes" feel native and delightful.  
- Runs 100% locally, zero cost, instant feedback. Matches your preference for local-first.

**Business Marketing Site Second (Priority #2)**  
- Public face for the business: Jacob OS as the product + service layer (local AI OS + small-business AI transformation using the tool catalog).  
- Can also showcase Cmap Nova and Conductor-LX as flagship tools.  
- High-signal content: Playbook excerpts, tool catalog, prospect case studies, "Save 10+ hours/week" framing.  
- Static or lightly dynamic, easy to iterate and host (Netlify/Vercel or self-hosted).

**Iteration Philosophy**  
- Phase 1 MVP in <2 hours of focused work.  
- Every phase ends with a working, viewable artifact.  
- Use reflection skill after each phase to capture learnings in playbook.  
- Add n8n-style canvas in later phase for workflow orchestration.  
- Always prefer real execution over planning.

**Tech Stack Recommendation**  
- **Local Hub**: Python + FastAPI (async, great DX) + Jinja2 templates + Tailwind CSS (via CDN for speed or built) + HTMX for interactivity. SQLite direct access. Simple uvicorn server.  
- **Business Site**: Astro or plain Vite + Tailwind (static export). Dark theme consistent. Optional: embed live demo of local hub if desired.  
- Why not PyQt for internal? Web is more flexible for n8n-style canvas, searchable MD, multi-view dashboards, and future collaboration.  
- Why not full n8n? You explicitly want local APIs/webhooks only.

**Risks & Mitigations**  
- Scope creep → Strict MVP per phase, ship then enhance.  
- Polish vs speed → Use Tailwind + proven dark tokens from Conductor-LX; copy patterns.  
- DB integration → Direct sqlite3 in FastAPI endpoints (simple, no ORM needed initially).

---

## Phased Implementation Plan

### Phase 0: Foundation & Design System (30 min)
- Create directory: `~/jacob-os/local-hub/`
- Define CSS design tokens in a `styles.css` (or Tailwind config) matching existing projects:
  - `--bg: #0e0e10; --surface: #16161a; --border: #2a2a30; --purple: #8b5cf6; --teal: #2dd4bf; etc.`
- Create `README.md` in local-hub with run instructions.
- Set up basic FastAPI skeleton (`main.py`, `templates/`, `static/`).
- Add `uvicorn` and `python-multipart` if needed (use existing Python env).
- **Deliverable**: Empty but styled shell running at http://localhost:8080 with nav and hero.

### Phase 1: Local Internal Hub — Core Views (MVP)
**Goal**: Working localhost site with playbook + prospects dashboard.

**Pages/Views**:
1. **Dashboard/Home** — Overview cards (active goals count, recent episodes, quick skill launchers, n8n-style status bar).
2. **Playbook** — Full rendered `PLAYBOOK.md` with nice typography, search bar (JS filter or server), collapsible sections, "100 pots" highlight callout. Add new entries form.
3. **Tool Catalog** — Render `tool-catalog.md` as filterable cards/table. Buttons: "Run in prospect audit", "Add to goals".
4. **Prospects** — Table from `contacts` table (name, company, score, tags, last_contact). Click row → modal with audit MD content. "New Prospect Audit" form that calls the skill.
5. **Goals** — CRUD list (type, title, horizon, status). Color-coded badges.
6. **Reflection Log** — List recent episodes + reflection outputs. Button to trigger nightly reflection.

**Backend**:
- FastAPI endpoints: `/api/playbook`, `/api/prospects`, `/api/goals`, `/api/run-skill/{name}`, `/api/reflect`.
- Direct SQLite queries (reuse context-read patterns).
- For skill execution: Subprocess call to Hermes or direct Python import of skills where possible. Fallback to terminal commands.

**Frontend Polish**:
- Sidebar nav with icons (use Lucide or inline SVG).
- Cards with left purple accent strip.
- Status pills: green/amber/coral/teal.
- Glassmorphism on modals/notifications.
- Bottom status bar: "Jacob OS v0.1 • Local • 47 records • Reflection last: 22:00".
- Responsive but desktop-optimized.

**Run Command**: `cd local-hub && python -m uvicorn main:app --reload --port 8080`

**Deliverable**: Fully functional site at localhost:8080. You can browse playbook, see prospects from Michael Truell audit, add goals, etc.

### Phase 2: Internal Tools Deepening (Build Out)
- Skill Launcher page: Visual cards for each Jacob OS skill (prospect-audit, identity-interview, reflection, context-read/write). Form inputs + "Execute" that streams output or shows result.
- n8n-style mini-canvas: Simple JS drag-and-drop or clickable nodes representing skills/workflows. Connect to launchers.
- Search across everything (playbook + DB + audits folder).
- Notifications system (toasts on skill completion, new prospect added).
- Export buttons (CSV for prospects, PDF for audits).
- Settings page: Config for Ollama models, API keys (masked), cron for reflection.
- **Iteration**: After 1 day of use, run reflection and update playbook with new patterns.

**Deliverable**: Mature internal operating system UI. Daily driver ready.

### Phase 3: Business Marketing Website
**Separate project**: `~/jacob-os/business-site/` (or `public/`).

**Pages**:
- **Landing/Hero**: Bold headline "Jacob OS — Your machine. Your intelligence. Compounding daily." Sub: Local-first AI OS + transformation toolkit for ambitious professionals and small businesses. CTA buttons: "Launch Local Hub", "Book Transformation Audit", "View Playbook".
- **How It Works**: 3-step visual (Install locally → Import your context → Agents compound knowledge).
- **Playbook & Principles**: Excerpt + link to full (or embed viewer).
- **Tool Catalog in Action**: Showcase 4-5 high-ROI tools with "Before/After" stories framed for Pocatello businesses (accounting, restaurants, law, retail).
- **Services**: Website modernization (n8n-style UX), AI automation implementation (Digits + Jasper + Calendly), Prospect-to-client pipeline, Cmap Nova + Conductor-LX bundles.
- **Case Studies**: Anonymized or real (after permission) from prospect audits.
- **Cmap Nova & Conductor-LX**: Featured tools section with download links/AppImage.
- **Footer/Contact**: Form or email.

**Tech**: Astro (or Vite + React/TS for future) + Tailwind. Build to static. Dark theme identical tokens. Add subtle animations (framer-motion if React).

**Polish**: Hero with subtle canvas preview (p5.js concept map or node connections). Badge pills everywhere. Glassmorphism on feature cards. Mobile-first but desktop beautiful.

**Hosting**: Netlify (free, instant deploys) or self-hosted on VPS. Domain later (jacobos.io or similar).

**Deliverable**: Live public site you can share. High-conversion marketing asset.

### Phase 4+: Advanced Iteration & Expansion
- Workflow Canvas (full n8n-style node editor for composing skills into agents).
- Voice integration (if TTS available).
- Cmap Nova integration: Embed or link concept maps for business processes.
- Conductor-LX deep link: Launch workspaces from web hub.
- Multi-user or shared memory (future).
- Analytics on your own usage (episodes count, skill frequency).
- Continuous: Every 5-10 iterations, update playbook, run reflection, ship a "vNext" release of the hub.

---

## Immediate Next Actions (Autonomous Execution)

I will now execute **Phase 0 + Phase 1 MVP** without further confirmation:

1. Scaffold `~/jacob-os/local-hub/` with FastAPI + Tailwind shell.
2. Implement playbook viewer + prospects table + basic dashboard.
3. Make it run and verify with real data from memory.db.
4. Create the business site scaffold in parallel or immediately after.
5. Report real tool output and URLs.

This follows the volume principle: ship working artifacts fast, iterate based on real use.

**Ready to begin?** (But per your preference: proceeding autonomously.)