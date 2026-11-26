#!/usr/bin/env bash
# Take a backup now, using the same job definition as the schedule.
set -euo pipefail
job="manual-backup-$(date +%s)"
kubectl -n library create job "$job" --from=cronjob/db-backup
kubectl -n library wait --for=condition=complete "job/$job" --timeout=180s
kubectl -n library logs "job/$job"
