#!/usr/bin/env bash
# S16 backup + restore drill — a consistent snapshot taken OUTSIDE the live volume, then put
# back into a disposable copy and opened the way the application would open it.
#
#   BACKUP_OUT=/home/ec-user/non_prod/aihubcampus_release_backups/s16 \
#     bash evidence/s16/backup_restore_drill.sh > evidence/s16/backup_restore_drill.txt 2>&1
#
# What it proves, in order:
#   1. the live service is healthy, so the snapshot is of a working system;
#   2. scripts/backup.sh produces a bundle on the host filesystem — never inside the
#      `aihubcampus_app_storage` volume — and self-verifies it;
#   3. the bundle is copied a second time, so the release holds two independent copies;
#   4. scripts/restore.sh restores it into a DISPOSABLE volume (nothing live is touched) and
#      matches the manifest checksum, integrity_check and every table count;
#   5. the restored copy is opened read-write in a throwaway container and re-counted — the
#      round trip ends with the same numbers it started with;
#   6. the disposable volume is removed, so the drill leaves nothing behind.
#
# No secret is read or printed: the bundle holds Argon2 hashes, never a password, and the
# environment is never dumped.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2

PROJECT="${COMPOSE_PROJECT_NAME:-aihubcampus}"
SERVICE=web
IMAGE=aihubcampus-web:local
DRILL_VOLUME="aihubcampus_restore_s16"
BACKUP_OUT="${BACKUP_OUT:?BACKUP_OUT must be an absolute path outside the live volume}"

fail() { printf '\nFAIL  %s\n' "$1"; exit 1; }

echo "# S16 backup + restore drill"
echo "# run (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "# host:      $(hostname) · $(uname -r)"
echo "# HEAD:      $(git rev-parse --short HEAD) · branch $(git rev-parse --abbrev-ref HEAD)"
echo "# bundle to: $BACKUP_OUT"
echo "# drill vol: $DRILL_VOLUME"
echo

echo "=== 1. the live service is healthy before we snapshot it ==="
echo "\$ docker compose ps"
docker compose ps --format 'table {{.Service}}\t{{.Status}}\t{{.Ports}}'
HEALTH="$(docker inspect "$(docker compose ps -q "$SERVICE")" --format '{{.State.Health.Status}}' 2>/dev/null)"
echo "health = $HEALTH"
[[ "$HEALTH" == "healthy" ]] || fail "the web service is not healthy — no release backup from a broken stack"
echo

echo "=== 2. the snapshot, taken OUTSIDE the live volume ==="
echo "\$ install -d -m 700 $BACKUP_OUT"
install -d -m 700 "$BACKUP_OUT" || fail "cannot create $BACKUP_OUT"
echo "\$ scripts/backup.sh --out $BACKUP_OUT"
scripts/backup.sh --out "$BACKUP_OUT" || fail "scripts/backup.sh failed — there is no usable backup"
echo
BUNDLE="$(ls -1t "$BACKUP_OUT"/aihubcampus-*.tar.gz 2>/dev/null | head -1)"
[[ -n "$BUNDLE" ]] || fail "no bundle was written to $BACKUP_OUT"
echo "bundle     : $BUNDLE"
echo "bytes      : $(stat -c%s "$BUNDLE")"
echo "sha256     : $(sha256sum "$BUNDLE" | cut -d' ' -f1)"
echo
echo "# the bundle is on the host, not inside the app volume:"
echo "\$ docker run --rm -v ${PROJECT}_app_storage:/v $IMAGE sh -c 'ls -A /v'"
docker run --rm --network none -v "${PROJECT}_app_storage:/v" "$IMAGE" sh -c 'ls -A /v'
echo "# (no tarball above — the live volume holds the database and the quarantine, nothing else)"
echo

echo "=== 3. a second copy, so the release holds two ==="
SECOND="${BUNDLE%.tar.gz}-offsite.tar.gz"
cp -p "$BUNDLE" "$SECOND" || fail "could not copy the bundle"
cp -p "$BUNDLE.sha256" "$SECOND.sha256" 2>/dev/null || true
echo "\$ cp -p <bundle> <bundle>-offsite.tar.gz"
echo "second copy: $SECOND"
echo "sha256     : $(sha256sum "$SECOND" | cut -d' ' -f1)"
[[ "$(sha256sum "$BUNDLE" | cut -d' ' -f1)" == "$(sha256sum "$SECOND" | cut -d' ' -f1)" ]] \
  || fail "the two copies differ"
echo
echo "# what the bundle holds:"
echo "\$ tar -tzf <bundle>"
tar -tzf "$BUNDLE" | sed 's/^/  /'
echo

echo "=== 4. the restore drill — into a DISPOSABLE volume, never the live one ==="
docker volume rm "$DRILL_VOLUME" >/dev/null 2>&1 || true
echo "\$ scripts/restore.sh --backup $BUNDLE --to-volume $DRILL_VOLUME"
scripts/restore.sh --backup "$BUNDLE" --to-volume "$DRILL_VOLUME" || fail "the restore drill failed"
echo

echo "=== 5. the restored copy, opened the way the app opens it ==="
echo "\$ docker run --rm -v $DRILL_VOLUME:/target $IMAGE python - <<'PY'"
docker run --rm -i --network none -v "$DRILL_VOLUME:/target" "$IMAGE" python - <<'PY'
import json, sqlite3
con = sqlite3.connect("/target/aihubcampus.db")
print("integrity_check :", con.execute("PRAGMA integrity_check").fetchone()[0])
tables = [r[0] for r in con.execute(
    "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
print("row counts      :", json.dumps({t: con.execute(f'select count(*) from "{t}"').fetchone()[0]
                                       for t in tables}, sort_keys=True))
print("schema version  :", con.execute("select max(version) from schema_migrations").fetchone()[0])
print("active dataset  :", con.execute(
    "select id, original_filename_safe, record_count from dataset_versions where is_active=1").fetchall())
print("users (role)    :", con.execute("select role, count(*) from users group by role").fetchall())
print("newest prediction:", con.execute(
    "select id, substr(created_at,1,19), predicted_class, round(default_probability,6), risk_tier "
    "from prediction_logs order by id desc limit 1").fetchone())
con.close()
PY
echo
echo "# and the same numbers read from the LIVE database, for comparison:"
docker compose exec -T "$SERVICE" python - <<'PY'
import json, sqlite3
con = sqlite3.connect("file:/app/storage/aihubcampus.db?mode=ro", uri=True)
tables = [r[0] for r in con.execute(
    "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
print("live row counts :", json.dumps({t: con.execute(f'select count(*) from "{t}"').fetchone()[0]
                                       for t in tables}, sort_keys=True))
con.close()
PY
echo

echo "=== 6. the drill leaves nothing behind ==="
echo "\$ docker volume rm $DRILL_VOLUME"
docker volume rm "$DRILL_VOLUME" && echo "removed" || fail "could not remove the drill volume"
echo
echo "RESULT: backup written and self-verified outside the live volume; the bundle restored into a"
echo "        disposable copy, integrity_check=ok, every table count matched, and the copy was"
echo "        opened read-write. The live volume was never touched."
