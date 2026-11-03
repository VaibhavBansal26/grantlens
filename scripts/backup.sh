#!/bin/sh
# Back up the database to backups/grantlens-<timestamp>.dump (pg_dump custom format, compressed).
#   scripts/backup.sh [keep]          keep = how many backups to retain (default 14)
# Defaults to the production stack; for the dev database run:
#   COMPOSE="docker compose -f docker-compose.yml" scripts/backup.sh
set -eu
COMPOSE="${COMPOSE:-docker compose -f docker-compose.prod.yml --env-file .env.prod}"
DIR="${BACKUP_DIR:-backups}"
KEEP="${1:-14}"
mkdir -p "$DIR"
out="$DIR/grantlens-$(date +%Y%m%d-%H%M%S).dump"

$COMPOSE exec -T db pg_dump -U grantlens -Fc grantlens > "$out.partial"
# A dump that cannot even be listed is not a backup: refuse to keep it.
if ! $COMPOSE exec -T db pg_restore --list < "$out.partial" > /dev/null; then
  rm -f "$out.partial"; echo "backup FAILED: the dump is unreadable" >&2; exit 1
fi
mv "$out.partial" "$out"
echo "backup written: $out ($(du -h "$out" | cut -f1))"

# Retention: delete everything older than the newest $KEEP backups.
ls -1t "$DIR"/grantlens-*.dump | awk -v k="$KEEP" 'NR > k' | while read -r old; do
  rm -f "$old"; echo "removed old backup: $old"
done
