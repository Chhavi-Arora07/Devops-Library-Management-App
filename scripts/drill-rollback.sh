#!/usr/bin/env bash
# Releases a deliberately broken version and checks that it is rolled back automatically.
# For staging only.
set -euo pipefail
url="${1:-http://localhost:8080}"
k() { kubectl -n library "$@"; }
path=/spec/template/spec/containers/0/env

original="$(k get rollout library -o 'jsonpath={.spec.template.spec.containers[0].env}')"
restore() {
  k patch rollout library --type=json \
    -p "[{\"op\":\"replace\",\"path\":\"$path\",\"value\":$original}]" >/dev/null
  kill "${load_pid:-0}" 2>/dev/null || true
}
trap restore EXIT

( while true; do curl -s -o /dev/null --max-time 2 "$url/api/books" || true; sleep 0.1; done ) &
load_pid=$!

k patch rollout library --type=json \
  -p "[{\"op\":\"add\",\"path\":\"$path/-\",\"value\":{\"name\":\"FAULT_RATE\",\"value\":\"0.8\"}}]"

for _ in $(seq 60); do
  sleep 10
  generation="$(k get rollout library -o 'jsonpath={.metadata.generation}')"
  observed="$(k get rollout library -o 'jsonpath={.status.observedGeneration}')"
  phase="$(k get rollout library -o 'jsonpath={.status.phase}')"
  echo "phase: $phase"
  [[ "$generation" == "$observed" ]] || continue
  if [[ "$phase" == Degraded ]]; then
    message="$(k get rollout library -o 'jsonpath={.status.message}')"
    # It must be the metrics that stopped it, not an unrelated problem.
    [[ "$message" == *"assessed Failed"* ]] || { echo "FAIL: $message" >&2; exit 1; }
    echo "PASS: the bad release was aborted"; exit 0
  fi
  stable="$(k get rollout library -o 'jsonpath={.status.stableRS}')"
  current="$(k get rollout library -o 'jsonpath={.status.currentPodHash}')"
  if [[ "$phase" == Healthy && "$stable" == "$current" ]]; then
    echo "FAIL: the bad release was promoted" >&2; exit 1
  fi
done
echo "FAIL: timed out" >&2; exit 1
