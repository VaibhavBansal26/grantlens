#!/bin/sh
# Tests scripts/deploy.sh against stand-ins for docker, git and curl: success, rollback, and a failed rollback.
#   sh scripts/test_deploy.sh
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
fail=0
ok() { echo "  ok    $1"; }
bad() { echo "  FAIL  $1"; fail=1; }

new_world() { # a scratch directory with fake tools; "bad tags" are listed in $W/bad
  W="$(mktemp -d)"; mkdir -p "$W/bin" "$W/scripts"
  cp "$HERE/deploy.sh" "$W/scripts/deploy.sh"
  printf '#!/bin/sh\nexit 0\n' > "$W/scripts/backup.sh"
  printf '#!/bin/sh\nexit 0\n' > "$W/scripts/smoke.sh"
  : > "$W/bad"; : > "$W/log"
  # docker: remember the tag of the last `up`, as the stack would be running that version
  printf '#!/bin/sh\necho "docker $*" >> "%s/log"\ncase "$*" in *" up "*) echo "$IMAGE_TAG" > "%s/live";; esac\n' "$W" "$W" > "$W/bin/docker"
  printf '#!/bin/sh\necho "git $*" >> "%s/log"\n' "$W" > "$W/bin/git"
  # curl: healthy unless the live tag is listed as bad
  printf '#!/bin/sh\n! grep -qx "$(cat "%s/live" 2>/dev/null)" "%s/bad"\n' "$W" "$W" > "$W/bin/curl"
  printf '#!/bin/sh\nexit 0\n' > "$W/bin/sleep"
  chmod +x "$W"/bin/* "$W"/scripts/*.sh
}
deploy() { (cd "$W" && PATH="$W/bin:$PATH" sh scripts/deploy.sh "$@" > out 2>&1) && rc=0 || rc=$?; }

echo "deploy.sh"
new_world; deploy abc123def4567890 v1
[ "$rc" = 0 ] && [ "$(cat "$W/.deploy_current")" = v1 ] && ok "a healthy deploy succeeds and records the tag" || bad "healthy deploy"
grep -q "checkout --quiet abc123def4567890" "$W/log" && ok "checks out the ref so compose files match the images" || bad "git checkout"
deploy def000 v2
[ "$rc" = 0 ] && [ "$(cat "$W/.deploy_current")" = v2 ] && ok "a second healthy deploy moves the pointer" || bad "second deploy"

echo v3 > "$W/bad"; deploy fff111 v3
[ "$rc" = 1 ] && [ "$(cat "$W/.deploy_current")" = v2 ] && [ "$(cat "$W/live")" = v2 ] && ok "an unhealthy deploy rolls back to the previous tag and fails" || bad "rollback"
grep -q "rolled back to v2" "$W/out" && ok "says what happened" || bad "rollback message"

printf 'v3\nv2\n' > "$W/bad"; deploy fff222 v3
[ "$rc" = 1 ] && grep -q "ALSO failed" "$W/out" && ok "reports a failed rollback loudly" || bad "failed rollback"

new_world; echo v1 > "$W/bad"; deploy aaa v1
[ "$rc" = 1 ] && grep -q "no previous version" "$W/out" && [ ! -f "$W/.deploy_current" ] && ok "a failed first deploy records nothing" || bad "first deploy failure"

new_world; (cd "$W" && DRY_RUN=1 PATH="$W/bin:$PATH" sh scripts/deploy.sh abc v9 > out 2>&1); 
grep -q "^+ " "$W/out" && [ ! -f "$W/.deploy_current" ] && [ ! -s "$W/log" ] && ok "DRY_RUN prints the steps and runs nothing" || bad "dry run"
exit $fail
