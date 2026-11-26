#!/usr/bin/env bash
# Proves a backup can be restored: write, back up, destroy, restore, verify. Staging only.
set -euo pipefail
dir="$(cd "$(dirname "$0")" && pwd)"
sql() { kubectl -n library exec postgres-0 -- psql -U library -d library -tAc "$1"; }

isbn="drill-$(date +%s)"
sql "INSERT INTO books (isbn,title,author,total_copies,available_copies)
     VALUES ('$isbn','Restore drill','ops',1,1)"
"$dir/backup.sh"
sql "DELETE FROM books WHERE isbn='$isbn'"
"$dir/restore.sh"
[[ "$(sql "SELECT count(*) FROM books WHERE isbn='$isbn'")" == 1 ]] \
  || { echo "FAIL: row was not restored" >&2; exit 1; }
sql "DELETE FROM books WHERE isbn='$isbn'"
echo "PASS: backup restored successfully"
