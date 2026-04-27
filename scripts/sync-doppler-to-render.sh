#!/usr/bin/env bash
# Sync Doppler prd secrets → Render upapply-api env vars
# Usage: ./scripts/sync-doppler-to-render.sh
# Requires: doppler CLI authenticated
set -euo pipefail

RENDER_SERVICE_ID="srv-d5hnmh6r433s73bsksg0"
RENDER_API_KEY="${RENDER_API_KEY:-rnd_wfmF6x9CPhGMnM2IVtbnvLicYMaF}"
RENDER_API="https://api.render.com/v1"

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

DOPPLER_FILE="$TMP_DIR/doppler.json"
CURRENT_FILE="$TMP_DIR/current.json"
MERGED_FILE="$TMP_DIR/merged.json"

echo "Fetching secrets from Doppler (upapply/prd)..."
doppler secrets download --project upapply --config prd --no-file --format json > "$DOPPLER_FILE"

echo "Fetching current Render env vars..."
curl -sf \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  "$RENDER_API/services/$RENDER_SERVICE_ID/env-vars" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(json.dumps([{'key': item['envVar']['key'], 'value': item['envVar']['value']} for item in data]))
" > "$CURRENT_FILE"

echo "Merging..."
python3 - "$DOPPLER_FILE" "$CURRENT_FILE" "$MERGED_FILE" <<'PYEOF'
import json, sys

doppler_path, current_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

with open(doppler_path) as f:
    doppler_raw = json.load(f)

with open(current_path) as f:
    current_list = json.load(f)

# Keys managed by Render infrastructure (don't overwrite)
render_managed = {'DATABASE_URL'}
# Build-time only (not needed in Render runtime)
skip_prefixes = ('DOPPLER_', 'VITE_')

merged = {item['key']: item['value'] for item in current_list}

for key, value in doppler_raw.items():
    if key in render_managed:
        continue
    if any(key.startswith(p) for p in skip_prefixes):
        continue
    merged[key] = value

with open(out_path, 'w') as f:
    json.dump([{'key': k, 'value': v} for k, v in merged.items()], f)

print(f"  {len(merged)} env vars ready to push")
PYEOF

echo "Pushing to Render..."
curl -sf -X PUT \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d @"$MERGED_FILE" \
  "$RENDER_API/services/$RENDER_SERVICE_ID/env-vars" > /dev/null

echo "Done. Trigger a deploy at: https://dashboard.render.com/web/$RENDER_SERVICE_ID"
