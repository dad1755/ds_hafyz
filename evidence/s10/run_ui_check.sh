#!/usr/bin/env bash
# S10 browser check driver.
#
# Starts a throwaway container of the freshly built image (its own storage volume, its own
# synthetic administrator and user), drives it with a real Chromium from the Playwright image,
# then removes everything it created. The deployment's own database is never written to.
#
#   bash evidence/s10/run_ui_check.sh > evidence/s10/browser_check.txt 2>&1
#
# Credentials are generated per run and never printed.
set -uo pipefail
cd "$(dirname "$0")/../.."

ROOT="$PWD"
OUT="$ROOT/evidence/s10"
CONTAINER="aihubcampus-s10-ui"
VOLUME="aihubcampus-s10-ui-storage"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1
  docker volume rm "$VOLUME" >/dev/null 2>&1
}
trap cleanup EXIT

ADMIN_USER="s10_browser_admin"
ADMIN_PASSWORD="$(openssl rand -hex 14)"
USER_USER="s10_browser_user"
USER_PASSWORD="$(openssl rand -hex 14)"

docker volume create "$VOLUME" >/dev/null
docker run -d --name "$CONTAINER" \
  --network aihubcampus_internal \
  -v "$VOLUME:/app/storage" \
  -v "$ROOT/data/UCI_Credit_Card.csv:/app/data/UCI_Credit_Card.csv:ro,z" \
  -e APP_DB_PATH=/app/storage/aihubcampus.db \
  -e APP_QUARANTINE_DIR=/app/storage/quarantine \
  aihubcampus-web:s10 >/dev/null

echo "throwaway container: $CONTAINER (volume $VOLUME, synthetic accounts, no secrets shown)"

for _ in $(seq 1 40); do
  if docker exec "$CONTAINER" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:2026/_stcore/health', timeout=2)" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "\$ docker exec <throwaway> python -c '<create a synthetic administrator and a synthetic user>'"
docker exec -e INITIAL_ADMIN_USERNAME="$ADMIN_USER" \
            -e INITIAL_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
       "$CONTAINER" python scripts/init_admin.py 2>&1 | tail -2
docker exec -i -e SYNTH_USER_USER="$USER_USER" -e SYNTH_USER_PASSWORD="$USER_PASSWORD" \
       "$CONTAINER" python - <<'PY'
import os
from src import db, security

connection = db.connect(os.environ.get("APP_DB_PATH", "/app/storage/aihubcampus.db"))
try:
    moment = db.to_iso(db.utcnow())
    with db.transaction(connection):
        connection.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, "
            "must_change_password, created_at, updated_at, last_login_at) "
            "VALUES (?, ?, ?, 'user', 1, 0, ?, ?, NULL)",
            (
                os.environ["SYNTH_USER_USER"],
                "S10 browser user",
                security.hash_password(os.environ["SYNTH_USER_PASSWORD"]),
                moment,
                moment,
            ),
        )
    print("synthetic user created (password not printed)")
finally:
    connection.close()
PY

METRICS_SHA="$(docker exec "$CONTAINER" sha256sum /app/models/metrics.json | cut -d' ' -f1)"
echo "metrics.json inside the image: sha256 $METRICS_SHA"

echo
echo "\$ docker run --rm --network aihubcampus_internal -v \"\$PWD/evidence/s10:/work:z\" -w /work \\"
echo "    -v <playwright modules>:/pw/node_modules:ro -e NODE_PATH=/pw/node_modules \\"
echo "    -e SYNTH_ADMIN_USER=<synthetic> -e SYNTH_ADMIN_PASSWORD=<synthetic> \\"
echo "    -e SYNTH_USER_USER=<synthetic> -e SYNTH_USER_PASSWORD=<synthetic> \\"
echo "    mcr.microsoft.com/playwright:v1.55.0-noble node ui_evaluation.js $CONTAINER 2026"
PW_CACHE="${PW_CACHE:-$HOME/.cache/s9-playwright}"
mkdir -p "$PW_CACHE"

docker run --rm --network aihubcampus_internal \
  -v "$OUT:/work:z" -w /work \
  -v "$PW_CACHE:/pw:ro,z" \
  -e NODE_PATH=/pw/node_modules \
  -e OUT_DIR=/work \
  -e METRICS_SHA="$METRICS_SHA" \
  -e SYNTH_ADMIN_USER="$ADMIN_USER" \
  -e SYNTH_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  -e SYNTH_USER_USER="$USER_USER" \
  -e SYNTH_USER_PASSWORD="$USER_PASSWORD" \
  mcr.microsoft.com/playwright:v1.55.0-noble \
  node ui_evaluation.js "$CONTAINER" 2026
echo "node exit=$?"
