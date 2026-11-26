#!/usr/bin/env bash
# Usage: deploy.sh <staging|production> <image>
# Applies the manifests, waits for the canary, and exits non-zero if it rolled back.
set -euo pipefail
env_name="${1:?environment}"; image="${2:?image}"
root="$(cd "$(dirname "$0")/.." && pwd)"
timeout="${TIMEOUT:-600}"

[[ -d "$root/k8s/overlays/$env_name" ]] || { echo "unknown environment: $env_name" >&2; exit 2; }

kubectl apply -k "$root/k8s/observability"
# The canary is judged on Prometheus data, so Prometheus must be up first.
kubectl -n observability rollout status deployment/prometheus --timeout=300s
kubectl kustomize "$root/k8s/overlays/$env_name" \
  | sed "s|image: library-app:dev|image: ${image}|g" \
  | kubectl apply -f -

jp() { kubectl -n library get rollout library -o "jsonpath={$1}"; }

deadline=$((SECONDS + timeout))
while ((SECONDS < deadline)); do
  if [[ "$(jp .status.observedGeneration)" == "$(jp .metadata.generation)" ]]; then
    phase="$(jp .status.phase)"
    if [[ "$phase" == Healthy && "$(jp .status.stableRS)" == "$(jp .status.currentPodHash)" ]]; then
      echo "release is healthy: $image"; exit 0
    fi
    if [[ "$phase" == Degraded ]]; then
      echo "release FAILED and was rolled back: $(jp .status.message)" >&2; exit 1
    fi
    echo "waiting: $phase $(jp .status.message)"
  fi
  sleep 10
done

echo "timed out, aborting the release" >&2
kubectl -n library patch rollout library --subresource=status --type=merge -p '{"status":{"abort":true}}'
exit 1
