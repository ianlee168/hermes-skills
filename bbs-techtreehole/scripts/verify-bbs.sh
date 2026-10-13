#!/bin/bash
# Quick verification: check if BBS is working (login returns 200 with actual content)
set -e

BBS_URL="${BBS_URL:-http://127.0.0.1:4567}"
MAX_WAIT="${MAX_WAIT:-60}"

echo "Checking BBS at $BBS_URL..."

# Wait for Ready
for i in $(seq 1 $MAX_WAIT); do
  if curl -s -o /dev/null -w '%{http_code}' "$BBS_URL/login" | grep -q '200'; then
    echo "✓ HTTP 200 on /login"
    break
  fi
  if [ $i -eq $MAX_WAIT ]; then
    echo "✗ Timeout waiting for /login 200"
    exit 1
  fi
  sleep 1
done

# Check it's not an error page
CONTENT=$(curl -s "$BBS_URL/login")
if echo "$CONTENT" | grep -q 'Failed to lookup view'; then
  echo "✗ Still showing error page (webpack bug not fixed)"
  exit 1
fi

if echo "$CONTENT" | grep -q 'nodebb.min.js'; then
  echo "✓ /login contains nodebb.min.js (build OK)"
else
  echo "✗ /login missing nodebb.min.js"
  exit 1
fi

echo "BBS is working correctly."