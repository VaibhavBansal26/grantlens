#!/bin/sh
# Replace the database with a backup. DESTRUCTIVE: the current database is dropped first.
#   scripts/restore.sh backups/grantlens-20260101-020000.dump --yes
set -eu
COMPOSE="${COMPOSE:-docker compose -f docker-compose.prod.yml --env-file .env.prod}"
file="${1:?usage: scripts/restore.sh <dump file> --yes}"
[ -f "$file" ] || { echo "no such file: $file" >&2; exit 1; }
if [ "${2:-}" != "--yes" ]; then
  echo "This DROPS the current database and replaces it with $file." >&2
  echo "Run it again with --yes to confirm." >&2
  exit 2
fi

$COMPOSE stop api web >/dev/null 2>&1 || true   # nothing may write while we swap the data
$COMPOSE exec -T db psql -U grantlens -d postgres -v ON_ERROR_STOP=1 \
  -c "DROP DATABASE IF EXISTS grantlens WITH (FORCE)" -c "CREATE DATABASE grantlens OWNER grantlens"
$COMPOSE exec -T db pg_restore -U grantlens -d grantlens --no-owner --exit-on-error < "$file"
$COMPOSE start api web >/dev/null 2>&1 || true
echo "restored $file"
