#!/usr/bin/env python3
"""
crm_import.py — promote a WARM prospect into Twenty CRM.  (runs on the VPS)

GTM rule this encodes: the CRM holds real pipeline, not a cold lead list. A prospect
lives in the registry + outreach queue (staged in the vault by the Mac's pipeline.py)
until it becomes real — a reply or a booked discovery call. THEN it earns a CRM record.

For each promoted prospect this creates, in Twenty (idempotently):
  - a Company            (name, website, city/state)
  - a Person             (the contact email, linked to the company)     [if email known]
  - an Opportunity       (early stage, linked to the company)
  - a Note               ("SEO Growth Plan" — the audit gaps + a pointer to the report
                          file in the vault), targeted to the company

Source of truth: the outreach queue staged at
  /srv/aios/vault/Business/prospect-data/intelligence_queue.json
Reports live at
  /srv/aios/vault/Business/seo-reports/<id>-<slug>.html

Auth: TWENTY_API_KEY from ~/personal-ai-os/.env, Twenty REST at http://127.0.0.1:8081
(the same pattern as platform/agent/services.py). Stdlib only — no pip deps.

Usage (dry-run is the DEFAULT — it writes nothing):
  python3 crm_import.py --from-vault                     # promote everyone replied/booked (dry-run)
  python3 crm_import.py --from-vault --status replied,booked
  python3 crm_import.py --ids poc-001,r013                # promote specific ids (dry-run)
  python3 crm_import.py --from-vault --status booked --commit   # actually write to Twenty
"""

import argparse, json, os, sys, urllib.request, urllib.error
from pathlib import Path

TWENTY_URL = "http://127.0.0.1:8081"
ENV_FILE = Path.home() / "personal-ai-os/.env"
VAULT = Path("/srv/aios/vault/Business")
QUEUE_JSON = VAULT / "prospect-data/intelligence_queue.json"
REPORTS_DIR = VAULT / "seo-reports"

STATE_ABBR = {  # region slug suffix -> state (extend as regions grow)
    "id": "Idaho", "ut": "Utah", "wy": "Wyoming", "mt": "Montana", "wa": "Washington",
    "or": "Oregon", "nv": "Nevada", "az": "Arizona", "co": "Colorado",
}


def load_env_key():
    if not ENV_FILE.exists():
        sys.exit(f"FATAL: {ENV_FILE} not found")
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("TWENTY_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("FATAL: TWENTY_API_KEY not in .env")


def api(method, path, key, body=None):
    url = TWENTY_URL + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {detail}")


def find_company_by_domain(key, url):
    """Idempotency: return existing company id whose domain matches, else None."""
    if not url:
        return None
    try:
        res = api("GET", "/rest/companies?limit=200", key)
    except Exception:
        return None
    host = url.split("//")[-1].split("/")[0].replace("www.", "").lower()
    for c in res.get("data", {}).get("companies", []):
        cu = (c.get("domainName") or {}).get("primaryLinkUrl", "")
        ch = cu.split("//")[-1].split("/")[0].replace("www.", "").lower()
        if ch and ch == host:
            return c["id"]
    return None


def state_from_region(region):
    if region and "-" in region:
        return STATE_ABBR.get(region.rsplit("-", 1)[-1], "")
    return ""


def report_pointer(pid):
    hits = sorted(REPORTS_DIR.glob(f"{pid}-*.html"))
    if not hits:
        return None
    name = hits[0].name
    return (f"Full SEO Growth Plan report: {REPORTS_DIR}/{name}\n"
            f"(Nextcloud: Vault/Business/seo-reports/{name})")


def build_company_body(e):
    body = {"name": e["name"]}
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


def note_body(e):
    a = e.get("audit", {})
    lines = [f"SEO audit: {a.get('gap','?')} ({a.get('audit_score','?')}/6)"]
    if a.get("signals"):
        lines.append("Findings: " + "; ".join(a["signals"][:8]))
    opp = e.get("opportunities", {})
    for k in ("seo", "ai", "geo"):
        if opp.get(k):
            lines.append(f"{k.upper()} opportunity: {opp[k]}")
    if e.get("est_retainer_monthly"):
        lines.append(f"Est. retainer: {e['est_retainer_monthly']}/mo")
    ptr = report_pointer(e["id"])
    if ptr:
        lines.append("")
        lines.append(ptr)
    return "\n".join(lines)


def promote(e, key, commit):
    tag = "COMMIT" if commit else "dry-run"
    print(f"\n◆ {e['name']}  [{tag}]")
    existing = find_company_by_domain(key, e.get("website", "")) if commit else None
    if existing:
        print(f"    company already in CRM ({existing}) — skipping create, will still add note")
        company_id = existing
    else:
        cbody = build_company_body(e)
        print(f"    POST /rest/companies  {json.dumps(cbody)}")
        company_id = None
        if commit:
            company_id = api("POST", "/rest/companies", key, cbody)["data"]["createCompany"]["id"]
            print(f"    → company {company_id}")

    email = (e.get("contact") or {}).get("email")
    if email:
        pbody = {"name": {"firstName": "", "lastName": e["name"][:60]},
                 "emails": {"primaryEmail": email}}
        if company_id:
            pbody["companyId"] = company_id
        print(f"    POST /rest/people      {json.dumps(pbody)}")
        if commit:
            pid = api("POST", "/rest/people", key, pbody)["data"]["createPerson"]["id"]
            print(f"    → person {pid}")

    obody = {"name": f"{e['name']} — local SEO/GEO retainer"}
    if company_id:
        obody["companyId"] = company_id
    print(f"    POST /rest/opportunities {json.dumps(obody)}")
    if commit:
        oid = api("POST", "/rest/opportunities", key, obody)["data"]["createOpportunity"]["id"]
        print(f"    → opportunity {oid}")

    nbody = {"title": f"SEO Growth Plan — {e['name']}", "bodyV2": {"markdown": note_body(e)}}
    print(f"    POST /rest/notes        (title: {nbody['title']})")
    if commit and company_id:
        note_id = api("POST", "/rest/notes", key, nbody)["data"]["createNote"]["id"]
        api("POST", "/rest/noteTargets", key, {"noteId": note_id, "targetCompanyId": company_id})
        print(f"    → note {note_id} linked to company")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-vault", action="store_true", help="read the staged outreach queue")
    ap.add_argument("--queue", help="explicit path to intelligence_queue.json (default: vault)")
    ap.add_argument("--status", default="replied,booked",
                    help="comma list; promote entries with a matching *_at timestamp (default replied,booked)")
    ap.add_argument("--ids", help="comma list of prospect ids to promote (overrides --status)")
    ap.add_argument("--commit", action="store_true", help="ACTUALLY write to Twenty (default: dry-run)")
    args = ap.parse_args()

    qpath = Path(args.queue) if args.queue else QUEUE_JSON
    if not qpath.exists():
        sys.exit(f"FATAL: queue not found at {qpath} — run the Mac's ./sync_vps.sh first")
    queue = json.loads(qpath.read_text())

    if args.ids:
        want = set(i.strip() for i in args.ids.split(","))
        picked = [e for e in queue if e["id"] in want]
    else:
        flags = [s.strip() for s in args.status.split(",")]
        picked = [e for e in queue if any(e.get(f"{s}_at") for s in flags)]

    key = load_env_key()
    print(f"Twenty CRM promotion — {len(picked)} prospect(s) selected "
          f"({'COMMIT' if args.commit else 'DRY-RUN, no writes'})")
    if not picked:
        print("Nothing to promote. A prospect qualifies once it has a replied_at / booked_at "
              "timestamp (or pass --ids). Cold prospects stay out of the CRM by design.")
        return
    for e in picked:
        promote(e, key, args.commit)
    print(f"\n{'✓ committed' if args.commit else '✓ dry-run complete — re-run with --commit to write'}: "
          f"{len(picked)} prospect(s)")


if __name__ == "__main__":
    main()
