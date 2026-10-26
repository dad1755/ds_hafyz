#!/usr/bin/env bash
# T11 at deployment level: a restart of the running service keeps the database, the model
# and a signed-in session.
#
#   bash evidence/s11/restart.sh
#
# It signs in as the demo user *inside the running container* (credentials come from the
# container's own environment and are never printed), records the row counts and the artifact
# checksum, recreates the container, waits for healthy, then resolves the same session token
# in a brand-new process and re-verifies the artifact. The token is held in a mode-600 host
# file and fed back on stdin, so it never appears in a command line or in this transcript. It
# is revoked at the end.
set -uo pipefail

REPO="/home/ec-user/non_prod/hafyz_ds"
cd "$REPO" || exit 1
TOKEN_FILE="$(mktemp "${TMPDIR:-/tmp}/s11-token-XXXXXX")"
chmod 600 "$TOKEN_FILE"
trap 'rm -f "$TOKEN_FILE"' EXIT

echo "\$ docker compose ps web"
docker compose ps web
echo

echo "\$ docker compose exec -T web python -m ml.verify_artifact --models-dir models"
docker compose exec -T web python -m ml.verify_artifact --models-dir models
echo "  exit=$?"
echo

echo "\$ docker compose exec -T web sha256sum models/best_pipeline.joblib"
docker compose exec -T web sha256sum models/best_pipeline.joblib
echo

echo "--- BEFORE the restart ---------------------------------------------------------"
echo "\$ docker compose exec -T web python -   # row counts from the live database"
docker compose exec -T web python - <<'PY'
import os
from src import db

conn = db.connect()
for table in ("users", "sessions", "prediction_logs", "dataset_versions", "audit_events"):
    n = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
    print(f"  {table:<18} {n}")
print(f"  db path            {os.environ['APP_DB_PATH']}")
PY
BEFORE_STARTED="$(docker inspect -f '{{.State.StartedAt}}' aihubcampus-web-1)"
echo "  container started  $BEFORE_STARTED"
echo

echo "\$ docker compose exec -T web python -   # sign in as the demo user, from container env"
docker compose exec -T web python - > "$TOKEN_FILE" <<'PY'
import os

from src import db, security

conn = db.connect()
principal, token = security.login(
    conn, os.environ["INITIAL_USER_USERNAME"], os.environ["INITIAL_USER_PASSWORD"]
)
print(f"signed in as {principal.username} role={principal.role} token_chars={len(token)}")
print(f"live sessions now: {conn.execute('SELECT COUNT(*) AS n FROM sessions WHERE revoked_at IS NULL').fetchone()['n']}")
print("TOKEN=" + token)
PY
echo "  exit=$?"
grep -v '^TOKEN=' "$TOKEN_FILE"
grep '^TOKEN=' "$TOKEN_FILE" | cut -d= -f2- > "${TOKEN_FILE}.raw"
mv "${TOKEN_FILE}.raw" "$TOKEN_FILE"
chmod 600 "$TOKEN_FILE"
echo "  token held on the host: $(stat -c 'mode %a, %s bytes' "$TOKEN_FILE") (value not printed)"
echo

echo "\$ docker compose up -d --force-recreate web"
docker compose up -d --force-recreate web
echo "  exit=$?"
echo

echo "--- waiting for healthy --------------------------------------------------------"
for attempt in $(seq 1 60); do
  state="$(docker inspect -f '{{.State.Health.Status}}' aihubcampus-web-1 2>/dev/null)"
  if [ "$state" = "healthy" ]; then
    echo "  healthy after ${attempt} poll(s)"
    break
  fi
  sleep 2
done
docker compose ps web
AFTER_STARTED="$(docker inspect -f '{{.State.StartedAt}}' aihubcampus-web-1)"
echo "  container started  $AFTER_STARTED"
if [ "$BEFORE_STARTED" != "$AFTER_STARTED" ]; then
  echo "  container was recreated: yes"
else
  echo "  container was recreated: NO"
fi
echo

echo "--- AFTER the restart ----------------------------------------------------------"
echo "\$ docker compose exec -T web python -   # the same row counts"
docker compose exec -T web python - <<'PY'
import os
from src import db

conn = db.connect()
for table in ("users", "sessions", "prediction_logs", "dataset_versions", "audit_events"):
    n = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
    print(f"  {table:<18} {n}")
print(f"  db path            {os.environ['APP_DB_PATH']}")
PY
echo

echo "\$ docker compose exec -T web python -c '<resolve the pre-restart token from stdin>' < token-file"
docker compose exec -T web python -c "import sys; from src import db, security; p = security.resolve_session(db.connect(), sys.stdin.read().strip()); print('session resolved after restart:', p.username, 'role=' + p.role); print('session ends:', p.session_expires_at.isoformat())" < "$TOKEN_FILE"
echo "  exit=$?"
echo

echo "\$ docker compose exec -T web python -m ml.verify_artifact --models-dir models"
docker compose exec -T web python -m ml.verify_artifact --models-dir models
echo "  exit=$?"
echo

echo "\$ docker compose exec -T web python -   # health from inside the container"
docker compose exec -T web python - <<'PY'
import urllib.request

print("  health:", urllib.request.urlopen("http://127.0.0.1:2026/_stcore/health", timeout=5).read().decode())
PY
echo
echo "\$ docker compose exec -T web python -c '<revoke the probe session>' < token-file"
docker compose exec -T web python -c "import sys; from src import db, security; token = sys.stdin.read().strip(); security.logout(db.connect(), token); print('probe session revoked')" < "$TOKEN_FILE"
echo "  exit=$?"
echo
echo "\$ docker inspect --format '{{json .NetworkSettings.Ports}}' aihubcampus-web-1"
docker inspect --format '{{json .NetworkSettings.Ports}}' aihubcampus-web-1
echo
echo "done"
