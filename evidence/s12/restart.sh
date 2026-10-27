#!/usr/bin/env bash
# S12 evidence — a real restart of the live stack preserves the data and the hardening.
#
# Records, before and after `docker compose up -d --force-recreate web`:
#   * the container id, start time and health
#   * the row count of every table (read from the live database, not from a backup)
#   * the database file size and mtime
#   * the model artifact sha256 as verified inside the container
#   * the hardening facts (read-only rootfs, dropped caps, uid, published ports)
#
# Run from the repo root:  bash evidence/s12/restart.sh 2>&1 | tee evidence/s12/restart.txt
set -uo pipefail

PROJECT="${COMPOSE_PROJECT_NAME:-aihubcampus}"
SERVICE="web"

counts() {
    docker compose -p "$PROJECT" exec -T "$SERVICE" python - <<'PY' 2>/dev/null | tr -d '\r'
import json, os, sqlite3
db = os.environ.get("APP_DB_PATH", "/app/storage/aihubcampus.db")
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
tables = [r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
print(json.dumps({t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}, sort_keys=True))
print("bytes:", os.path.getsize(db), "mtime:", int(os.stat(db).st_mtime))
con.close()
PY
}

snapshot() {
    local label="$1" cid
    cid="$(docker compose -p "$PROJECT" ps -q "$SERVICE")"
    echo "--- $label ---"
    echo "container     : ${cid:0:12}"
    echo "started       : $(docker inspect --format '{{.State.StartedAt}}' "$cid")"
    echo "health        : $(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cid")"
    echo "uid           : $(docker exec "$cid" id -u) ($(docker exec "$cid" id -un))"
    echo "read_only     : $(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$cid")"
    echo "cap_drop      : $(docker inspect --format '{{json .HostConfig.CapDrop}}' "$cid")"
    echo "security_opt  : $(docker inspect --format '{{json .HostConfig.SecurityOpt}}' "$cid")"
    echo "tmpfs         : $(docker inspect --format '{{json .HostConfig.Tmpfs}}' "$cid")"
    echo "port bindings : $(docker inspect --format '{{json .HostConfig.PortBindings}}' "$cid")"
    echo "docker port   : '$(docker port "$cid" 2>/dev/null)'"
    echo "image         : $(docker inspect --format '{{.Image}}' "$cid")"
    echo "artifact      : $(docker exec "$cid" python -c 'import hashlib;print(hashlib.sha256(open("/app/models/best_pipeline.joblib","rb").read()).hexdigest())' 2>/dev/null | tr -d '\r')"
    echo "row counts    : $(counts | head -1)"
    echo "db            : $(counts | tail -1)"
    echo
}

echo "AI Hub Campus S12 — restart persistence — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo
snapshot "BEFORE"

echo "=== docker compose up -d --force-recreate $SERVICE ==="
docker compose -p "$PROJECT" up -d --force-recreate "$SERVICE" 2>&1
echo

# Wait for the health probe rather than sleeping a fixed time.
for i in $(seq 1 30); do
    sleep 2
    status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$(docker compose -p "$PROJECT" ps -q "$SERVICE")" 2>/dev/null)"
    echo "poll $i: $status"
    [[ "$status" == "healthy" ]] && break
done
echo
snapshot "AFTER"
