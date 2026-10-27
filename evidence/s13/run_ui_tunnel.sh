#!/usr/bin/env bash
# S13 browser check driver — the whole journey, through the public HTTPS endpoint.
#
#   bash evidence/s13/run_ui_tunnel.sh > evidence/s13/browser_check.txt 2>&1
#
# What it does, in order:
#   1. generates a throwaway password for a synthetic administrator and inserts that account
#      into the live database (the operator's admin cannot be used: it is seeded with
#      must_change_password=1 and its credential must not be rewritten);
#   2. builds a 500-row CSV prefix of the seed dataset to upload through the dataset manager;
#   3. drives https://www.aihubcampus.online with a real Chromium — three journeys, listed at
#      the top of ui_tunnel.js;
#   4. deactivates the synthetic administrator, whatever the browser run returned.
#
# No secret is printed: the synthetic password lives in a mode-600 file under the scratch
# directory, is read by node, and is removed by the EXIT trap. The operator's and the demo
# user's credentials are read by node straight from .env and are never placed in a command
# line or in the transcript.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2

ROOT="$PWD"
OUT="$ROOT/evidence/s13"
SCRATCH="${SCRATCH_DIR:?SCRATCH_DIR must be set to a private scratch directory}"
BASE_URL="${BASE_URL:-https://www.aihubcampus.online}"
SYNTH_USER="s13_tunnel_check"
NODE_MODULES="${NODE_MODULES:-/home/ec-user/qa759-v2/node_modules}"

mkdir -p "$SCRATCH" "$OUT"
chmod 700 "$SCRATCH"

CRED_FILE="$SCRATCH/s13_creds.json"
UPLOAD_CSV="$SCRATCH/s13_upload_subset.csv"

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

echo "# S13 — the public HTTPS surface, driven end to end by a real browser"
echo "# run (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "# target:     $BASE_URL"
echo "# host:       $(hostname) · $(uname -r)"
echo

echo "\$ docker compose exec -T -e SYNTH_ADMIN_USER=<synthetic> -e SYNTH_ADMIN_PASSWORD=<synthetic> web python - < evidence/s13/make_synth_admin.py"
docker compose exec -T \
  -e SYNTH_ADMIN_USER="$SYNTH_USER" -e SYNTH_ADMIN_PASSWORD="$SYNTH_PASSWORD" \
  web python - < "$OUT/make_synth_admin.py" 2>&1 | tail -2
echo

echo "\$ python3 evidence/s13/make_upload_subset.py <scratch>/s13_upload_subset.csv 500"
python3 evidence/s13/make_upload_subset.py "$UPLOAD_CSV" 500
echo

echo "\$ docker compose ps"
docker compose ps --format 'table {{.Service}}\t{{.Name}}\t{{.Status}}\t{{.Ports}}'
echo
echo "\$ docker inspect --format '{{.Image}}' aihubcampus-web-1 aihubcampus-cloudflared-1"
docker inspect --format '{{.Name}} image={{.Image}}' aihubcampus-web-1 aihubcampus-cloudflared-1
echo
echo "\$ curl -sS -o /dev/null -w '<status> <content-type> <server>' https://www.aihubcampus.online/"
for target in https://www.aihubcampus.online/ https://aihubcampus.online/ https://www.aihubcampus.online/_stcore/health http://www.aihubcampus.online/; do
  curl -sS -o /dev/null --max-time 25 \
    -w "$target -> status=%{http_code} type=%{content_type} redirect=%{redirect_url}\n" "$target"
done
echo

echo "\$ NODE_PATH=$NODE_MODULES BASE_URL=$BASE_URL CRED_FILE=<scratch>/s13_creds.json UPLOAD_CSV=<scratch>/s13_upload_subset.csv node evidence/s13/ui_tunnel.js"
NODE_PATH="$NODE_MODULES" \
BASE_URL="$BASE_URL" \
CRED_FILE="$CRED_FILE" \
UPLOAD_CSV="$UPLOAD_CSV" \
OUT_DIR="$OUT" \
  node "$OUT/ui_tunnel.js"
NODE_EXIT=$?
echo "node exit=$NODE_EXIT"
echo

echo "\$ docker compose exec -T -e SYNTH_ADMIN_USER=<synthetic> web python - < evidence/s13/deactivate_synth_admin.py"
docker compose exec -T -e SYNTH_ADMIN_USER="$SYNTH_USER" \
  web python - < "$OUT/deactivate_synth_admin.py" 2>&1 | tail -2

exit "$NODE_EXIT"
