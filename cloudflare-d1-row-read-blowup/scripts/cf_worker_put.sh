#!/usr/bin/env bash
# Upload a pre-bundled ES-module Worker via the Cloudflare API.
# The filename= on the module part is REQUIRED; without it Cloudflare returns
# 10021 "Uncaught Error: No such module: index.js" even for a hello-world.
#
# Usage: cf_worker_put.sh <account_id> <script_name> <module.js> <metadata.json> <email> <api_key>
#
# metadata.json must repeat compatibility_date and EVERY existing binding
# (read them first from .../workers/scripts/<name>/settings), otherwise they
# are silently dropped by the upload.
set -eu
AID="$1"; NAME="$2"; MODULE="$3"; META="$4"; EMAIL="$5"; KEY="$6"

python3 -c "import json,sys;json.load(open(sys.argv[1]))" "$META"   # fail fast on bad JSON

HTTP=$(curl -sS -o /tmp/_cf_put.json -w '%{http_code}' --max-time 180 \
  -X PUT "https://api.cloudflare.com/client/v4/accounts/$AID/workers/scripts/$NAME" \
  -H "X-Auth-Email: $EMAIL" -H "X-Auth-Key: $KEY" \
  -F "metadata=@$META;type=application/json" \
  -F "index.js=@$MODULE;filename=index.js;type=application/javascript+module")
echo "HTTP $HTTP"
python3 -c "import json;d=json.load(open('/tmp/_cf_put.json'));print('success:',d.get('success'));print('errors:',json.dumps(d.get('errors'),ensure_ascii=False)[:400])"
