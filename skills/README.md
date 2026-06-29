# Bundled skills

Generic skills baked into every deployment. Per-customer bespoke skills are
packaged as a separate plugin (see plugin-customizer), not forked in here.

| Skill | Role |
|-------|------|
| onboarding-interview | **Customization engine.** Interviews each tenant (who are you, what does the business do, top headaches, tools) → writes context files + starter workflows. |
| prime | Loads all context files at session start. Default for every tenant. |
| self-assessment | Finds the tenant's highest-ROI automations. Doubles as agency discovery/upsell. |
| plugin-customizer / create-plugin | Build/tailor bespoke per-customer skills as a plugin. |
| smb-pack (optional) | Small-business skills (invoice-chase, lead-triage, month-end...). Off by default. |

Drop the actual skill folders here during Phase 0.
