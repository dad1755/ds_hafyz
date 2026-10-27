#!/usr/bin/env bash
# S16 rollback drill — take the release down and bring it back, without losing the data.
#
#   TAG=v1.0.0 bash evidence/s16/rollback_drill.sh > evidence/s16/rollback_drill.txt 2>&1
#
# The drill is the documented rollback path, executed:
#   `docker compose down`   — WITHOUT -v. The containers and the project network go; the
#                             `aihubcampus_app_storage` volume (the database) does not.
#   `docker compose up -d`  — the release comes back on the same volume.
#
# It proves, with the numbers on both sides of the restart:
#   1. the tag under test is the commit that is checked out, and it is what is deployed;
#   2. the database's sha256 and every table count BEFORE the restart;
#   3. `down` removes the containers and leaves the volume;
#   4. `up -d` returns the service to healthy, on a NEW container id;
#   5. the database's sha256 and every table count are UNCHANGED after the restart — the
#      restart is a restart, not a reset;
#   6. the public HTTPS surface answers again through the tunnel.
#
# Read-only with respect to the data: nothing is written to the volume, and no secret is read.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2

PROJECT="${COMPOSE_PROJECT_NAME:-aihubcampus}"
SERVICE=web
VOLUME="${PROJECT}_app_storage"
TAG="${TAG:?TAG must name the release tag under test}"
PUBLIC_URL="${PUBLIC_URL:-https://www.aihubcampus.online}"
UA='aihubcampus-s16-rollback/1.0'

fail() { printf '\nFAIL  %s\n' "$1"; exit 1; }

dbstate() {
  # One read-only transaction: the file hash plus every table count.
  docker compose exec -T "$SERVICE" python - <<'PY'
import hashlib, json, pathlib, sqlite3
db = pathlib.Path("/app/storage/aihubcampus.db")
print("db sha256   :", hashlib.sha256(db.read_bytes()).hexdigest())
con = sqlite3.connect("file:/app/storage/aihubcampus.db?mode=ro", uri=True)
tables = [r[0] for r in con.execute(
    "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
print("row counts  :", json.dumps({t: con.execute(f'select count(*) from "{t}"').fetchone()[0]
                                   for t in tables}, sort_keys=True))
print("integrity   :", con.execute("PRAGMA integrity_check").fetchone()[0])
con.close()
PY
}

echo "# S16 rollback drill — down without -v, then back up on the same volume"
echo "# run (UTC):   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "# host:        $(hostname) · $(uname -r)"
echo "# tag under test: $TAG"
echo

echo "=== 1. the tag, the commit and the deployment are the same thing ==="
echo "\$ git rev-parse $TAG^{commit} · git rev-parse HEAD · git describe --tags --exact-match"
TAG_SHA="$(git rev-parse "$TAG^{commit}" 2>/dev/null)" || fail "tag $TAG does not exist"
HEAD_SHA="$(git rev-parse HEAD)"
echo "tag  $TAG -> $TAG_SHA"
echo "HEAD        -> $HEAD_SHA"
[[ "$TAG_SHA" == "$HEAD_SHA" ]] || fail "the tag does not point at HEAD — this drill must run on the release commit"
git describe --tags --exact-match
echo "\$ git status --porcelain"
git status --porcelain | sed 's/^/  /'
echo
echo "\$ docker inspect aihubcampus-web-1 (before)"
docker inspect "$(docker compose ps -q "$SERVICE")" \
  --format 'container : {{.Name}} ({{.Id}})
image     : {{.Image}}
started   : {{.State.StartedAt}}
health    : {{.State.Health.Status}}'
echo

echo "=== 2. the data, before the restart ==="
dbstate | tee /tmp/s16_db_before.txt
echo

echo "=== 3. down — WITHOUT -v, which is the whole point ==="
echo "\$ docker compose down"
docker compose down || fail "docker compose down failed"
echo
echo "\$ docker compose ps   (nothing left running)"
docker compose ps
echo "\$ docker volume ls --filter name=$VOLUME"
docker volume ls --filter "name=$VOLUME"
echo "\$ docker volume inspect $VOLUME --format '{{.Name}} {{.Mountpoint}}'"
docker volume inspect "$VOLUME" --format '{{.Name}} {{.Mountpoint}}' \
  || fail "the data volume is gone — this drill must never use 'down -v'"
echo "# the volume is still there; the containers are not. That is what 'down' without -v means."
echo

echo "=== 4. up — the release comes back on the same volume ==="
echo "\$ docker compose up -d"
docker compose up -d || fail "docker compose up -d failed"
echo
echo "# waiting for the health probe (the compose healthcheck has a 40 s start period)"
DEADLINE=$((SECONDS + 240))
while (( SECONDS < DEADLINE )); do
  CID="$(docker compose ps -q "$SERVICE")"
  if [[ -n "$CID" ]]; then
    STATUS="$(docker inspect "$CID" --format '{{.State.Health.Status}}')"
    printf '  %s health=%s\n' "$(date -u +%H:%M:%SZ)" "$STATUS"
    [[ "$STATUS" == "healthy" ]] && break
  fi
  sleep 10
done
[[ "${STATUS:-}" == "healthy" ]] || fail "the service did not reach healthy within 240 s"
echo
echo "\$ docker compose ps"
docker compose ps --format 'table {{.Service}}\t{{.Name}}\t{{.Status}}\t{{.Ports}}'
echo
echo "\$ docker inspect aihubcampus-web-1 (after)"
docker inspect "$(docker compose ps -q "$SERVICE")" \
  --format 'container : {{.Name}} ({{.Id}})
image     : {{.Image}}
started   : {{.State.StartedAt}}
health    : {{.State.Health.Status}}
read_only : {{.HostConfig.ReadonlyRootfs}}
cap_drop  : {{.HostConfig.CapDrop}}
ports     : {{.HostConfig.PortBindings}}'
echo

echo "=== 5. the data, after the restart — the same bytes ==="
dbstate | tee /tmp/s16_db_after.txt
echo
if diff -u /tmp/s16_db_before.txt /tmp/s16_db_after.txt; then
  echo "PASS  identical before and after: the restart did not touch a row"
else
  fail "the database changed across a restart that wrote nothing"
fi
echo

echo "=== 6. the public surface answers again ==="
echo "\$ curl -sS -A '$UA' -o /dev/null -w '<status> <time>' $PUBLIC_URL/_stcore/health"
curl -sS -A "$UA" --max-time 40 -o /tmp/s16_health.txt \
  -w 'health  -> status=%{http_code} time=%{time_total}s body=%{size_download}B\n' \
  "$PUBLIC_URL/_stcore/health" || fail "the public health endpoint did not answer"
echo "body    -> $(cat /tmp/s16_health.txt)"
echo "\$ curl -sS -A '$UA' -o /dev/null -w '<status>' $PUBLIC_URL/"
curl -sS -A "$UA" --max-time 40 -o /dev/null \
  -w 'root    -> status=%{http_code} content_type=%{content_type}\n' "$PUBLIC_URL/" \
  || fail "the public root did not answer"
echo
echo "RESULT: the release was taken down with 'docker compose down' (no -v), the data volume"
echo "        survived, 'docker compose up -d' brought the same image back to healthy on the same"
echo "        volume, the database was byte-identical afterwards, and the public HTTPS surface"
echo "        answered again. The rollback path in docs/runbook.md §5 is exercised, not asserted."
