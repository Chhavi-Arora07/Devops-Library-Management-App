#!/usr/bin/env bash
# Usage: restore.sh [file-name]   (default: the newest backup)
# Replaces the current data with the backup, in a single transaction.
set -euo pipefail
file="${1:-latest}"
[[ "$file" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid file name" >&2; exit 2; }
job="restore-$(date +%s)"

kubectl -n library get cronjob db-backup -o json | python3 -c '
import json, sys
name, wanted = sys.argv[1], sys.argv[2]
spec = json.load(sys.stdin)["spec"]["jobTemplate"]["spec"]
spec["backoffLimit"] = 0
c = spec["template"]["spec"]["containers"][0]
c["name"] = "restore"
c["env"].append({"name": "FILE", "value": wanted})
c["args"] = ["""
if [ "$FILE" = latest ]; then path=$(ls -1t /backups/*.dump | head -n 1)
else path="/backups/$FILE"; fi
echo "restoring $path"
pg_restore --clean --if-exists --single-transaction -d "$DATABASE_URL" "$path"
"""]
json.dump({"apiVersion": "batch/v1", "kind": "Job",
           "metadata": {"name": name, "namespace": "library"}, "spec": spec}, sys.stdout)
' "$job" "$file" | kubectl apply -f -

kubectl -n library wait --for=condition=complete "job/$job" --timeout=180s
kubectl -n library logs "job/$job"
