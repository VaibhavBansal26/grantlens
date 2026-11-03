#!/bin/sh
# Post-deploy checks against a running stack. Exits non-zero if any check fails.
#   scripts/smoke.sh http://localhost:3100            basic checks (read-only)
#   scripts/smoke.sh http://localhost:3100 --limits   also checks the rate limiter ignores a forged
#                                                     X-Forwarded-For (this locks YOUR address out of login for ~1 minute)
set -u
BASE="${1:?usage: scripts/smoke.sh <base url> [--limits]}"
fail=0
check() { # description, command...
  desc="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "  ok    $desc"; else echo "  FAIL  $desc"; fail=1; fi
}
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
hdr() { curl -s -D- -o /dev/null "$BASE/api/health" | tr -d '\r' | grep -i "^$1:" ; }

echo "smoke test: $BASE"
check "front page loads"                       test "$(code "$BASE/")" = 200
check "API health through the proxy"           test "$(code "$BASE/api/health")" = 200
check "anonymous session endpoint"             sh -c "curl -s '$BASE/api/auth/me' | grep -q '\"user\":null'"
check "unknown API path is a JSON error"       sh -c "curl -s '$BASE/api/definitely-not-here' | grep -q '\"error\"'"
check "login required for private endpoints"   test "$(code "$BASE/api/saved-searches")" = 401
check "security header: nosniff"               hdr x-content-type-options
check "security header: no-referrer"           hdr referrer-policy
check "responses carry a request id"           hdr x-request-id
check "responses are not cached"               sh -c "curl -s -D- -o /dev/null '$BASE/api/health' | grep -qi 'cache-control: no-store'"
check "search works"                           sh -c "curl -s '$BASE/api/search?q=cancer&k=3' | grep -q '\"results\"'"

if [ "${2:-}" = "--limits" ]; then
  echo "rate limiting:"
  limited=0
  for i in $(seq 1 14); do
    c=$(curl -s -o /dev/null -w '%{http_code}' -H "X-Forwarded-For: 203.0.113.$i" -H 'Content-Type: application/json' \
        -d '{"email":"smoke-test@example.invalid","password":"not a real password"}' "$BASE/api/auth/login")
    [ "$c" = 429 ] && limited=$((limited + 1))
  done
  # 14 attempts, each claiming a different address: if the forgery worked, none would be limited.
  check "forged X-Forwarded-For does not dodge the login limit ($limited of 14 limited)" test "$limited" -ge 3
fi

[ "$fail" = 0 ] && echo "all checks passed" || { echo "SOME CHECKS FAILED"; exit 1; }
