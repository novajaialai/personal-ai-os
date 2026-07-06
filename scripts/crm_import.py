#!/usr/bin/env python3
"""
crm_import.py — sync prospects into Twenty CRM.  (runs on the VPS)

Model (corrected 2026-07-05): every prospect belongs in the CRM from first contact so
that ALL outreach + touchpoints are tracked in one place — Company + Person + an
`outreachStage` lifecycle field (Cold → Contacted → Replied → Booked → Client). A deal
**Opportunity** is created ONLY once the prospect becomes real (Replied / Booked); that
keeps the pipeline forecast honest while still tracking every cold touch. (Contacts ≠ deals.)

Idempotent via a sync-map in the vault (prospect id -> Twenty ids); re-run any time and it
updates stages instead of duplicating. Source queue is staged by the Mac's pipeline.py /
sync_vps.sh into /srv/aios/vault/Business/prospect-data/intelligence_queue.json.

Auth: TWENTY_API_KEY from ~/personal-ai-os/.env; Twenty REST at http://127.0.0.1:8081.
Stdlib only. DRY-RUN by default — pass --commit to write.

Usage:
  python3 crm_import.py --sync                          # all prospects (dry-run)
  python3 crm_import.py --sync --min-stage contacted    # only those in active outreach
  python3 crm_import.py --sync --commit                 # write to Twenty
  python3 crm_import.py --ids poc-001,r022 --commit
"""

import argparse, json, sys, time, urllib.request, urllib.error
from pathlib import Path

TWENTY_URL = "http://127.0.0.1:8081"
ENV_FILE = Path.home() / "personal-ai-os/.env"
VAULT = Path("/srv/aios/vault/Business")
QUEUE_JSON = VAULT / "prospect-data/intelligence_queue.json"
SYNC_MAP = VAULT / "prospect-data/crm_sync_map.json"
REPORTS_DIR = VAULT / "seo-reports"

STAGES = ["COLD", "CONTACTED", "REPLIED", "BOOKED", "CLIENT", "PASSED"]
STAGE_RANK = {s: i for i, s in enumerate(["COLD", "CONTACTED", "REPLIED", "BOOKED", "CLIENT"])}
STATE_ABBR = {"id": "Idaho", "ut": "Utah", "wy": "Wyoming", "mt": "Montana", "wa": "Washington",
              "or": "Oregon", "nv": "Nevada", "az": "Arizona", "co": "Colorado"}


def load_env_key():
    if not ENV_FILE.exists():
        sys.exit(f"FATAL: {ENV_FILE} not found")
    for line in ENV_FILE.read_text().splitlines():
        if line.strip().startswith("TWENTY_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("FATAL: TWENTY_API_KEY not in .env")


_PACE = 0.7          # seconds between calls -> ~85/min, under Twenty's 100-per-60s limit
_last = [0.0]

def api(method, path, key, body=None):
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(4):
        wait = _PACE - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        req = urllib.request.Request(TWENTY_URL + path, data=data, method=method, headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                print("    (rate limited — backing off 62s)")
                time.sleep(62)
                continue
            raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:300]}")


def stage_of(e):
    if e.get("status") == "passed":
        return "PASSED"
    if e.get("status") == "client":
        return "CLIENT"
    if e.get("booked_at"):
        return "BOOKED"
    if e.get("replied_at"):
        return "REPLIED"
    if e.get("sent_at"):
        return "CONTACTED"
    return "COLD"


def state_from_region(region):
    if region and "-" in region:
        return STATE_ABBR.get(region.rsplit("-", 1)[-1], "")
    return ""


def company_body(e, stage):
    body = {"name": e["name"], "outreachStage": stage}
    url = e.get("website", "")
    if url.startswith("http"):
        body["domainName"] = {"primaryLinkUrl": url}
    addr = {}
    if e.get("city"):
        addr["addressCity"] = e["city"]
    st = state_from_region(e.get("region", ""))
    if st:
        addr["addressState"] = st
    if addr:
        addr["addressCountry"] = "United States"
        body["address"] = addr
    return body


def note_markdown(e):
    a = e.get("audit", {})
    lines = [f"**SEO audit:** {a.get('gap','?')} ({a.get('audit_score','?')}/6)"]
    if a.get("signals"):
        lines.append("Findings: " + "; ".join(a["signals"][:8]))
    opp = e.get("opportunities", {})
    for k in ("seo", "ai", "geo"):
        if opp.get(k):
            lines.append(f"- **{k.upper()}:** {opp[k]}")
    if e.get("est_retainer_monthly"):
        lines.append(f"- Est. retainer: {e['est_retainer_monthly']}/mo")
    hits = sorted(REPORTS_DIR.glob(f"{e['id']}-*.html"))
    if hits:
        lines.append(f"\nGrowth Plan report: `{REPORTS_DIR}/{hits[0].name}` "
                     f"(Nextcloud → Vault/Business/seo-reports/{hits[0].name})")
    return "\n".join(lines)


def has_real_email(e):
    c = e.get("contact") or {}
    return bool(c.get("email")) and c.get("confidence") == "high"


def sync_one(e, key, smap, commit):
    pid = e["id"]
    stage = stage_of(e)
    rec = smap.get(pid, {})
    verb = "update" if rec.get("company") else "create"
    print(f"  {e['name']:<32} → {stage:<9} [{verb}]")

    # Company (create or update stage)
    if rec.get("company"):
        if commit:
            api("PATCH", f"/rest/companies/{rec['company']}", key, {"outreachStage": stage})
        cid = rec["company"]
    else:
        if commit:
            cid = api("POST", "/rest/companies", key, company_body(e, stage))["data"]["createCompany"]["id"]
            rec["company"] = cid
        else:
            cid = None
        # SEO report note — once, on first creation
        if commit and cid:
            note_id = api("POST", "/rest/notes", key,
                          {"title": f"SEO Growth Plan — {e['name']}",
                           "bodyV2": {"markdown": note_markdown(e)}})["data"]["createNote"]["id"]
            api("POST", "/rest/noteTargets", key, {"noteId": note_id, "targetCompanyId": cid})
            rec["note"] = note_id

    # Person — only when we have a REAL (non-guessed) email
    if has_real_email(e) and not rec.get("person"):
        pbody = {"name": {"firstName": "", "lastName": e["name"][:60]},
                 "emails": {"primaryEmail": e["contact"]["email"]}}
        if rec.get("company"):
            pbody["companyId"] = rec["company"]
        print(f"      + contact {e['contact']['email']}")
        if commit:
            rec["person"] = api("POST", "/rest/people", key, pbody)["data"]["createPerson"]["id"]

    # Opportunity — ONLY once the prospect is real (Replied / Booked)
    if stage in ("REPLIED", "BOOKED", "CLIENT") and not rec.get("opportunity"):
        obody = {"name": f"{e['name']} — local SEO/GEO retainer",
                 "stage": "MEETING" if stage in ("BOOKED", "CLIENT") else "NEW"}
        if rec.get("company"):
            obody["companyId"] = rec["company"]
        print(f"      + OPPORTUNITY (stage {obody['stage']}) — real deal")
        if commit:
            rec["opportunity"] = api("POST", "/rest/opportunities", key, obody)["data"]["createOpportunity"]["id"]

    rec["stage"] = stage
    if commit:
        smap[pid] = rec


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sync", action="store_true", help="upsert prospects at/above --min-stage")
    ap.add_argument("--min-stage", default="cold", choices=[s.lower() for s in STAGE_RANK],
                    help="only sync prospects at/above this stage (default cold = everyone)")
    ap.add_argument("--ids", help="comma list of prospect ids (overrides --sync selection)")
    ap.add_argument("--queue", help="queue path (default: vault)")
    ap.add_argument("--commit", action="store_true", help="ACTUALLY write to Twenty (default dry-run)")
    args = ap.parse_args()

    qpath = Path(args.queue) if args.queue else QUEUE_JSON
    if not qpath.exists():
        sys.exit(f"FATAL: queue not found at {qpath} — run the Mac's ./sync_vps.sh first")
    queue = json.loads(qpath.read_text())
    smap = json.loads(SYNC_MAP.read_text()) if SYNC_MAP.exists() else {}

    if args.ids:
        want = set(i.strip() for i in args.ids.split(","))
        picked = [e for e in queue if e["id"] in want]
    else:
        floor = STAGE_RANK[args.min_stage.upper()]
        picked = [e for e in queue if STAGE_RANK.get(stage_of(e), 0) >= floor]

    key = load_env_key()
    mode = "COMMIT" if args.commit else "DRY-RUN (no writes)"
    print(f"CRM sync — {len(picked)} prospect(s), min-stage={args.min_stage} — {mode}\n")
    if not picked:
        print("Nothing selected.")
        return

    from collections import Counter
    dist = Counter(stage_of(e) for e in picked)
    for e in picked:
        sync_one(e, key, smap, args.commit)
        if args.commit:
            SYNC_MAP.write_text(json.dumps(smap, indent=2))   # crash-safe: persist after each
    print(f"\nStage distribution: {dict(dist)}")
    opps = sum(1 for e in picked if stage_of(e) in ("REPLIED", "BOOKED", "CLIENT"))
    print(f"{'✓ committed' if args.commit else '✓ dry-run — re-run with --commit'}: "
          f"{len(picked)} companies, {opps} opportunit{'y' if opps==1 else 'ies'} (deals only for real prospects)")
    if args.commit:
        print(f"sync-map: {SYNC_MAP}")


if __name__ == "__main__":
    main()
