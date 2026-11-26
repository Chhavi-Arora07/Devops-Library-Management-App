#!/usr/bin/env bash
# Read-only checks, safe to run against production.
set -euo pipefail
base="${1:-http://localhost:8080}"

check() { # path expected-status
  code="$(curl -s -o /dev/null -w '%{http_code}' --retry 10 --retry-delay 3 --retry-all-errors \
          --max-time 5 "$base$1")" || true
  [[ "$code" == "$2" ]] || { echo "FAIL $1: got $code, wanted $2" >&2; exit 1; }
  echo "ok   $1 -> $code"
}

check /healthz 200
check /readyz 200
check / 200
check /api/books 200
check /api/members 401
