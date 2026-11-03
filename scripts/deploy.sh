#!/bin/sh
# Deploy a published version on the production host, with a backup first and an automatic rollback.
#   scripts/deploy.sh <git ref> [image tag]     image tag defaults to the first 12 characters of the ref
# Needs: docker compose, git, curl, a filled-in .env.prod (including GHCR_OWNER), and, if the images are private,
# a one-time `docker login ghcr.io` with a token that can read packages.
#   DRY_RUN=1   print what would run, change nothing
#   BACKUP=0    skip the pre-deploy database backup (the first deploy has no database yet)
# Database migrations run when the new API starts and are additive, so rolling the images back is safe; if a
# migration itself went wrong, restore the backup that was just taken (scripts/restore.sh).
set -eu
REF="${1:?usage: scripts/deploy.sh <git ref> [image tag]}"
TAG="${2:-$(printf '%s' "$REF" | cut -c1-12)}"
COMPOSE="docker compose -f docker-compose.prod.yml -f docker-compose.images.yml --env-file .env.prod"
PORT="${HTTP_PORT:-80}"
CURRENT=.deploy_current

run() { if [ "${DRY_RUN:-0}" = 1 ]; then echo "+ $*"; else "$@"; fi; }
up() { IMAGE_TAG="$1" run $COMPOSE pull && IMAGE_TAG="$1" run $COMPOSE up -d --no-build --remove-orphans; }
healthy() {
  [ "${DRY_RUN:-0}" = 1 ] && return 0
  for _ in $(seq 1 90); do
    curl -sf "http://127.0.0.1:$PORT/api/health" > /dev/null && sh scripts/smoke.sh "http://127.0.0.1:$PORT" && return 0
    sleep 2
  done
  return 1
}

previous=""
[ -f "$CURRENT" ] && previous="$(cat "$CURRENT")"
echo "deploying $REF as image tag $TAG (currently: ${previous:-nothing})"

run git fetch --quiet origin
run git checkout --quiet "$REF"   # keep the compose files and scripts in step with the images
[ "${BACKUP:-1}" = 0 ] || run sh scripts/backup.sh

if up "$TAG" && healthy; then
  [ "${DRY_RUN:-0}" = 1 ] || echo "$TAG" > "$CURRENT"
  echo "deployed $TAG"
  exit 0
fi

echo "deploy of $TAG FAILED" >&2
if [ -n "$previous" ] && [ "$previous" != "$TAG" ]; then
  echo "rolling back to $previous" >&2
  up "$previous" && healthy && { echo "rolled back to $previous; $TAG is NOT live" >&2; exit 1; }
  echo "rollback to $previous ALSO failed: check '$COMPOSE logs'" >&2
else
  echo "no previous version to roll back to: check '$COMPOSE logs'" >&2
fi
exit 1
