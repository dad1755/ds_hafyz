#!/usr/bin/env bash
# S15 demo rehearsal driver — the demo script, executed end to end against the live URL.
#
#   SCRATCH_DIR=<private dir> bash evidence/s15/run_demo_rehearsal.sh > evidence/s15/demo_rehearsal.txt 2>&1
#
# What it does, in order:
#   1. generates a throwaway password for a synthetic administrator and inserts that account
#      into the live database (the operator's account belongs to the operator, and this sprint
#      must not rewrite its credential);
#   2. writes the two CSVs the dataset step uploads: one that breaks the 25-column contract and
#      must be refused, one valid file that must be staged;
#   3. drives https://www.aihubcampus.online with a real Chromium through the demo script's
#      steps — administrator sign-in, user management, dataset validation, user sign-in, the 23
#      preset values, the scored result, an invalid submission, model evaluation, sign-out —
#      timing each step and writing one screenshot per step;
#   4. deactivates the synthetic administrator, whatever the browser run returned.
#
# No secret is printed: the synthetic password lives in a mode-600 file under the scratch
# directory, is read by node, and is removed by the EXIT trap. The demo user's credential is
# read by node straight from .env and is never placed in a command line or in the transcript.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2

ROOT="$PWD"
OUT="$ROOT/evidence/s15"
SCRATCH="${SCRATCH_DIR:?SCRATCH_DIR must be set to a private scratch directory}"
BASE_URL="${BASE_URL:-https://www.aihubcampus.online}"
SYNTH_USER="s15_demo_check"
NODE_MODULES="${NODE_MODULES:-/home/ec-user/qa759-v2/node_modules}"

mkdir -p "$SCRATCH" "$OUT"
chmod 700 "$SCRATCH"

CRED_FILE="$SCRATCH/s15_creds.json"

cleanup() {
  rm -f "$CRED_FILE"
}
trap cleanup EXIT

SYNTH_PASSWORD="$(openssl rand -hex 16)"
python3 - "$CRED_FILE" "$SYNTH_USER" "$SYNTH_PASSWORD" <<'PY'
import json, sys
path, username, password = sys.argv[1:4]
with open(path, "w", encoding="utf-8") as handle:
    json.dump({"username": username, "password": password}, handle)
PY
chmod 600 "$CRED_FILE"

echo "# S15 — the demo script, rehearsed end to end against the live URL"
echo "# run (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "# target:     $BASE_URL"
echo "# host:       $(hostname) · $(uname -r)"
echo "# HEAD:       $(git rev-parse --short HEAD) · branch $(git rev-parse --abbrev-ref HEAD)"
echo

echo "\$ docker compose ps"
docker compose ps --format 'table {{.Service}}\t{{.Name}}\t{{.Status}}\t{{.Ports}}'
echo
echo "\$ curl -sS -o /dev/null -w '<status>' $BASE_URL/_stcore/health"
curl -sS -o /dev/null --max-time 25 -w "health -> status=%{http_code} time=%{time_total}s\n" \
  "$BASE_URL/_stcore/health"
echo

echo "\$ docker compose exec -T -e SYNTH_ADMIN_USER=<synthetic> -e SYNTH_ADMIN_PASSWORD=<synthetic> web python - < evidence/s15/make_demo_admin.py"
docker compose exec -T \
  -e SYNTH_ADMIN_USER="$SYNTH_USER" -e SYNTH_ADMIN_PASSWORD="$SYNTH_PASSWORD" \
  web python - < "$OUT/make_demo_admin.py" 2>&1 | tail -2
echo

# Row count is a parameter because the manager rejects identical bytes by checksum: a repeat run
# with the same count correctly answers "already version #N — nothing new was staged".
ROWS="${REHEARSAL_ROWS:-300}"
echo "\$ python3 evidence/s15/make_demo_uploads.py <scratch> $ROWS"
python3 evidence/s15/make_demo_uploads.py "$SCRATCH" "$ROWS" 
echo

echo "\$ NODE_PATH=$NODE_MODULES BASE_URL=$BASE_URL CRED_FILE=<scratch>/s15_creds.json node evidence/s15/ui_demo_rehearsal.js"
NODE_PATH="$NODE_MODULES" \
BASE_URL="$BASE_URL" \
CRED_FILE="$CRED_FILE" \
VALID_CSV="$SCRATCH/rehearsal_valid_subset.csv" \
INVALID_CSV="$SCRATCH/rehearsal_invalid_missing_column.csv" \
OUT_DIR="$OUT" \
  node "$OUT/ui_demo_rehearsal.js"
NODE_EXIT=$?
echo "node exit=$NODE_EXIT"
echo

echo "\$ docker compose exec -T -e SYNTH_ADMIN_USER=<synthetic> web python - < evidence/s15/deactivate_demo_admin.py"
docker compose exec -T -e SYNTH_ADMIN_USER="$SYNTH_USER" \
  web python - < "$OUT/deactivate_demo_admin.py" 2>&1 | tail -2

exit "$NODE_EXIT"
