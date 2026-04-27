#!/usr/bin/env bash
# Sync Doppler prd secrets → Render upapply-api env vars
# Usage: ./scripts/sync-doppler-to-render.sh
# Requires: doppler CLI authenticated, RENDER_API_KEY set (or reads from Doppler)
set -euo pipefail

RENDER_SERVICE_ID="srv-d5hnmh6r433s73bsksg0"
RENDER_API_KEY="${RENDER_API_KEY:-rnd_wfmF6x9CPhGMnM2IVtbnvLicYMaF}"
RENDER_API="https://api.render.com/v1"

echo "Fetching secrets from Doppler (upapply/prd)..."
SECRETS=$(doppler secrets download --project upapply --config prd --no-file --format json 2>/dev/null)

# Build the env var array for Render (exclude Doppler meta vars)
ENV_VARS=$(echo "$SECRETS" | python3 -c "
import json, sys
secrets = json.load(sys.stdin)
skip = {'DOPPLER_PROJECT', 'DOPPLER_CONFIG', 'DOPPLER_ENVIRONMENT'}
# Render doesn't need VITE_ vars (those are build-time only)
skip.update({k for k in secrets if k.startswith('VITE_')})
result = [{'key': k, 'value': v} for k, v in secrets.items() if k not in skip]
print(json.dumps(result))
")

echo "Fetching current Render env vars..."
CURRENT=$(curl -sf \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  "$RENDER_API/services/$RENDER_SERVICE_ID/env-vars" | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(json.dumps([{'key': item['envVar']['key'], 'value': item['envVar']['value']} for item in data]))
")

# Merge: Render-managed vars (DATABASE_URL from fromDatabase) stay as-is
MERGED=$(python3 -c "
import json, sys
doppler = json.loads('''$ENV_VARS''')
current = json.loads('''$CURRENT''')

# Keys managed by Render infrastructure (don't overwrite)
render_managed = {'DATABASE_URL'}

current_map = {item['key']: item['value'] for item in current}
doppler_map = {item['key']: item['value'] for item in doppler}

merged = dict(current_map)
for k, v in doppler_map.items():
    if k not in render_managed:
        merged[k] = v

print(json.dumps([{'key': k, 'value': v} for k, v in merged.items()]))
")

echo "Pushing merged env vars to Render..."
curl -sf -X PUT \
  -H "Authorization: Bearer $RENDER_API_KEY" \
  -H "Content-Type: application/json" \
  -d "$MERGED" \
  "$RENDER_API/services/$RENDER_SERVICE_ID/env-vars" > /dev/null

echo "Done. Render env vars updated from Doppler prd."
echo "Trigger a new deploy at: https://dashboard.render.com/web/$RENDER_SERVICE_ID"
