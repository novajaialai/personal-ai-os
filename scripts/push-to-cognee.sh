#!/usr/bin/env bash
# push-to-cognee.sh — ingest a directory of docs into the VPS Cognee reasoning index.
#
# The vault (markdown, git, Nextcloud) is the SYSTEM OF RECORD; Cognee is a DERIVED
# reasoning index built from it. This script is the sync: point it at any dir and it
# (re)ingests every .md/.txt into a Cognee dataset, then rebuilds that dataset's graph.
# Re-run anytime — cognee upserts by content, so it's safe to run repeatedly.
#
# Usage:
#   push-to-cognee.sh <path> [dataset] [--no-cognify]
#   push-to-cognee.sh /srv/aios/vault/Business business            # a vault section
#   push-to-cognee.sh /srv/aios/vault vault                        # the whole vault
#   push-to-cognee.sh ~/projects/business-plan business_plan       # a repo
#
# Defaults: dataset = basename of <path>. Cognify runs in the background.
set -euo pipefail

PATH_IN="${1:?usage: push-to-cognee.sh <path> [dataset] [--no-cognify]}"
DATASET="${2:-$(basename "$PATH_IN")}"
[ "${2:-}" = "--no-cognify" ] && DATASET="$(basename "$PATH_IN")"
NO_COGNIFY=0; for a in "$@"; do [ "$a" = "--no-cognify" ] && NO_COGNIFY=1; done

COGNEE="http://127.0.0.1:8011"
# key lives at ~/.cognee/api_key.json on the VPS, ~/.cognee-plugin/api_key.json on the Mac
KEY=$(python3 - <<'PY'
import json, os
for p in ("~/.cognee/api_key.json", "~/.cognee-plugin/api_key.json"):
    p = os.path.expanduser(p)
    if os.path.exists(p):
        print(json.load(open(p))["api_key"]); break
else:
    raise SystemExit("no cognee api_key.json found")
PY
)

[ -d "$PATH_IN" ] || { echo "no such dir: $PATH_IN" >&2; exit 1; }

# stage flattened copies so nested files keep distinct, readable names in the graph
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
count=0
while IFS= read -r f; do
  rel="${f#"$PATH_IN"/}"
  flat=$(printf '%s' "$rel" | tr '/' '__')
  cp "$f" "$STAGE/$flat"
  count=$((count+1))
done < <(find "$PATH_IN" -type f \( -name '*.md' -o -name '*.txt' \) -not -path '*/.git/*' 2>/dev/null)

[ "$count" -gt 0 ] || { echo "no .md/.txt files under $PATH_IN — nothing to push" >&2; exit 0; }
echo "→ pushing $count docs from $PATH_IN into cognee dataset '$DATASET'"

# POST /add (multipart, all files at once)
ARGS=(); for f in "$STAGE"/*; do ARGS+=(-F "data=@$f"); done
add=$(curl -s -X POST "$COGNEE/api/v1/add" -H "X-Api-Key: $KEY" \
      "${ARGS[@]}" -F "datasetName=$DATASET" -F "run_in_background=false")
echo "  add: $(printf '%s' "$add" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("status","?"))' 2>/dev/null || echo '?')"

if [ "$NO_COGNIFY" -eq 1 ]; then
  echo "  (skipping cognify — data added, graph not rebuilt)"; exit 0
fi

# POST /cognify (build/refresh the graph, in background)
cog=$(curl -s -X POST "$COGNEE/api/v1/cognify" -H "X-Api-Key: $KEY" \
      -H "Content-Type: application/json" -d "{\"datasets\":[\"$DATASET\"],\"runInBackground\":true}")
rid=$(printf '%s' "$cog" | python3 -c 'import sys,json;d=json.load(sys.stdin);print(next(iter(d.values())).get("pipeline_run_id","?"))' 2>/dev/null || echo '?')
echo "  cognify: started (run $rid) — graph builds in background on the OpenRouter free chain"
echo "  check:  curl -s $COGNEE/api/v1/datasets/status -H \"X-Api-Key: \$KEY\""
