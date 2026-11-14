#!/usr/bin/env bash
# Smoke test of the running trust stack, through the mTLS gateway.
# Needs: `make trust-keys`, then `docker compose up -d postgres opa dev-idp elasticsearch boundary discovery gateway`.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CERTS="$ROOT/tools/dev-ca/out"
GATEWAY="https://localhost:8443"
IDP="http://127.0.0.1:8090"
PRODUCT="risk-compliance.risk-scores"
READ="$GATEWAY/products/$PRODUCT/rows?columns=fraud_score&purpose=fraud-review"
TLS=(--max-time 15 --cacert "$CERTS/ca/ca.pem" --cert "$CERTS/notebook.pem" --key "$CERTS/notebook.key")

token() { curl -fsS --max-time 10 -X POST "$IDP/token/$1" | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])'; }
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

ANALYST="$(token risk-analyst)"
OWNER="$(token risk-owner)"

echo "no client certificate         -> $(code --max-time 15 --cacert "$CERTS/ca/ca.pem" -H "Authorization: Bearer $ANALYST" "$READ")  (expect 400)"
echo "certificate, no token         -> $(code "${TLS[@]}" "$READ")  (expect 401)"
# A purpose no grant covers, so this check holds even after an earlier run left a grant behind.
NO_GRANT="$GATEWAY/products/$PRODUCT/rows?columns=fraud_score&purpose=smoke-no-grant"
echo "token, no grant               -> $(code "${TLS[@]}" -H "Authorization: Bearer $ANALYST" "$NO_GRANT")  (expect 403)"

REQUEST=$(curl -fsS "${TLS[@]}" -H "Authorization: Bearer $ANALYST" -H 'Content-Type: application/json' \
  -X POST "$GATEWAY/api/access-requests" \
  -d '{"data_product_id":"'"$PRODUCT"'","justification":"fraud review","purpose":"fraud-review","requested_columns":["fraud_score"]}')
ID=$(echo "$REQUEST" | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
echo "access request $ID            -> $(echo "$REQUEST" | python3 -c 'import sys,json;print(json.load(sys.stdin)["status"])')"

echo "owner approves $ID            -> $(code "${TLS[@]}" -H "Authorization: Bearer $OWNER" -X POST "$GATEWAY/api/access-requests/$ID/approve?ttl_days=1")  (expect 200)"
echo "token + grant                 -> $(code "${TLS[@]}" -H "Authorization: Bearer $ANALYST" "$READ")  (expect 200, masked)"
