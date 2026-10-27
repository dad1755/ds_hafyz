#!/usr/bin/env bash
# S16 final live smoke — HTTPS, both roles end to end, and the probability against the artifact.
#
#   bash evidence/s16/run_release_smoke.sh > evidence/s16/live_smoke.txt 2>&1
#
# What it does, in order:
#   1. probes the public HTTPS surface with curl (status, edge headers, health body) and proves
#      no origin port is published;
#   2. scores the 23 demonstrator values DIRECTLY from the shipped artifact, two ways — the
#      application's own CLI (`python -m src.inference`, which loads the verified pipeline and
#      never touches Streamlit) and a bare scikit-learn `predict_proba` on a one-row frame in
#      manifest feature order. The two must agree, and both are printed;
#   3. creates a synthetic administrator for the run (the operator's own account is the
#      operator's, and this smoke must not rewrite its credential);
#   4. writes the CSV that breaks the 25-column contract, which the admin journey uploads and
#      must see refused;
#   5. drives https://www.aihubcampus.online with a real Chromium through both roles and
#      compares the probability ON SCREEN with the number from step 2;
#   6. deactivates the synthetic administrator, whatever the browser run returned.
#
# No secret is printed: the synthetic password lives in a mode-600 file under the scratch
# directory and is removed by the EXIT trap; the demo user's credential is read from .env by
# node and never placed in a command line or in this transcript.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2

ROOT="$PWD"
OUT="$ROOT/evidence/s16"
SCRATCH="${SCRATCH_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/s16-smoke.XXXXXXXX")}"
BASE_URL="${BASE_URL:-https://www.aihubcampus.online}"
SYNTH_USER="s16_release_check"
NODE_MODULES="${NODE_MODULES:-/home/ec-user/qa759-v2/node_modules}"
UA='aihubcampus-s16-smoke/1.0'
CRED_FILE="$SCRATCH/s16_creds.json"
REQUEST="$SCRATCH/demo_request.json"
INVALID_CSV="$SCRATCH/invalid_missing_column.csv"

mkdir -p "$SCRATCH" "$OUT"
chmod 700 "$SCRATCH"
cleanup() { rm -f "$CRED_FILE"; rm -rf "$SCRATCH"; }
trap cleanup EXIT

echo "# S16 final live smoke — HTTPS, both roles, and the probability against the artifact"
echo "# run (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "# target:    $BASE_URL"
echo "# host:      $(hostname) · $(uname -r)"
echo "# HEAD:      $(git rev-parse --short HEAD) · branch $(git rev-parse --abbrev-ref HEAD)"
echo "# tag:       $(git tag --points-at HEAD | paste -sd, - | sed 's/^$/none/')"
echo

echo "=== 1. the public HTTPS surface ==="
echo "\$ docker compose ps"
docker compose ps --format 'table {{.Service}}\t{{.Name}}\t{{.Status}}\t{{.Ports}}'
echo
echo "\$ docker port aihubcampus-web-1   (must be empty: no host port, Gate E)"
docker port "$(docker compose ps -q web)" || true
echo "  (empty output above = nothing published)"
echo
echo "\$ curl -sS -A '$UA' -D - -o /dev/null $BASE_URL/"
curl -sS -A "$UA" --max-time 40 -D "$SCRATCH/headers.txt" -o /dev/null -w \
  'status=%{http_code} content_type=%{content_type} time=%{time_total}s\n' "$BASE_URL/"
grep -iE '^(server|cf-ray|strict-transport-security|content-type):' "$SCRATCH/headers.txt" | sed 's/^/  /'
echo
echo "\$ curl -sS -A '$UA' $BASE_URL/_stcore/health"
curl -sS -A "$UA" --max-time 40 -w '\n  status=%{http_code} time=%{time_total}s\n' \
  "$BASE_URL/_stcore/health"
echo

echo "=== 2. the artifact's own answer for the 23 demonstrator values ==="
python3 - "$REQUEST" <<'PY'
import json, sys
demo = {"LIMIT_BAL": 120000, "SEX": 2, "EDUCATION": 2, "MARRIAGE": 2, "AGE": 34,
        "PAY_0": 2, "PAY_2": 2, "PAY_3": 0, "PAY_4": 0, "PAY_5": -1, "PAY_6": -1,
        "BILL_AMT1": 35000, "BILL_AMT2": 33500, "BILL_AMT3": 30000, "BILL_AMT4": 28000,
        "BILL_AMT5": 26500, "BILL_AMT6": 25000,
        "PAY_AMT1": 2000, "PAY_AMT2": 2500, "PAY_AMT3": 3000, "PAY_AMT4": 3000,
        "PAY_AMT5": 3500, "PAY_AMT6": 4000}
open(sys.argv[1], "w").write(json.dumps(demo))
print("request written:", len(demo), "features")
PY
echo
echo "# (a) the application's own CLI — verified pipeline, no Streamlit in the path"
echo "\$ docker compose exec -T web python -m src.inference --input - < request.json"
docker compose exec -T web python -m src.inference --input - < "$REQUEST" > "$SCRATCH/cli.json" 2>&1
cat "$SCRATCH/cli.json"
echo
echo "# (b) a bare scikit-learn predict_proba on the same artifact, feature order from the manifest"
echo "\$ { python body with the request inlined } | docker compose exec -T web python -"
{
  cat <<'PY'
import json
PY
  printf 'row = json.loads(r"""%s""")\n' "$(cat "$REQUEST")"
  cat <<'PY'
import joblib, pandas as pd
manifest = json.load(open("/app/models/model_manifest.json"))
order = manifest["features"]["order"]
pipeline = joblib.load("/app/models/best_pipeline.joblib")
frame = pd.DataFrame([{name: row[name] for name in order}], columns=order)
proba = pipeline.predict_proba(frame)[0]
print("feature order  :", " ".join(order))
print("columns match  :", list(frame.columns) == order)
print("predict_proba  :", [round(float(x), 12) for x in proba])
print("P(class 1)     :", repr(float(proba[1])))
print("argmax         :", int(pipeline.predict(frame)[0]))
PY
} | docker compose exec -T web python -
echo

# The two independent computations must agree; the browser check compares the screen to (a).
EXPECT_PROB="$(python3 - "$SCRATCH/cli.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))["probability"])
PY
)"
EXPECT_CLASS="$(python3 - "$SCRATCH/cli.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))["predicted_class"])
PY
)"
EXPECT_MODEL="$(python3 - "$SCRATCH/cli.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))["model_version"])
PY
)"
echo "expected (from the artifact): probability=$EXPECT_PROB class=$EXPECT_CLASS model=$EXPECT_MODEL"
echo

echo "=== 3. a synthetic administrator for the run ==="
SYNTH_PASSWORD="$(openssl rand -hex 16)"
python3 - "$CRED_FILE" "$SYNTH_USER" "$SYNTH_PASSWORD" <<'PY'
import json, sys
path, username, password = sys.argv[1:4]
with open(path, "w", encoding="utf-8") as handle:
    json.dump({"username": username, "password": password}, handle)
PY
chmod 600 "$CRED_FILE"
echo "\$ docker compose exec -T -e SYNTH_ADMIN_USER=<synthetic> -e SYNTH_ADMIN_PASSWORD=<synthetic> web python - < evidence/s15/make_demo_admin.py"
docker compose exec -T \
  -e SYNTH_ADMIN_USER="$SYNTH_USER" -e SYNTH_ADMIN_PASSWORD="$SYNTH_PASSWORD" \
  web python - < "$ROOT/evidence/s15/make_demo_admin.py" 2>&1 | tail -2
echo

echo "=== 4. the CSV that must be refused ==="
echo "\$ python3 - (drop one feature column from the 25-column contract, keep 3 rows)"
python3 - "$INVALID_CSV" <<'PY'
import csv, sys
src = "data/UCI_Credit_Card.csv"
with open(src, newline="", encoding="utf-8") as handle:
    reader = csv.reader(handle)
    header = next(reader)
    rows = [next(reader) for _ in range(3)]
drop = header.index("PAY_AMT6")
header = [h for i, h in enumerate(header) if i != drop]
rows = [[v for i, v in enumerate(r) if i != drop] for r in rows]
with open(sys.argv[1], "w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(header)
    writer.writerows(rows)
print(f"wrote {sys.argv[1]}: {len(header)} columns (PAY_AMT6 removed), {len(rows)} rows")
PY
echo

echo "=== 5. both roles, end to end, through the live URL ==="
echo "\$ NODE_PATH=$NODE_MODULES BASE_URL=$BASE_URL CRED_FILE=<scratch> node evidence/s16/ui_release_smoke.js"
NODE_PATH="$NODE_MODULES" \
BASE_URL="$BASE_URL" \
CRED_FILE="$CRED_FILE" \
INVALID_CSV="$INVALID_CSV" \
EXPECT_PROB="$EXPECT_PROB" \
EXPECT_CLASS="$EXPECT_CLASS" \
EXPECT_MODEL="$EXPECT_MODEL" \
OUT_DIR="$OUT" \
  node "$OUT/ui_release_smoke.js"
NODE_EXIT=$?
echo "node exit=$NODE_EXIT"
echo

echo "=== 6. the synthetic administrator is deactivated ==="
echo "\$ docker compose exec -T -e SYNTH_ADMIN_USER=<synthetic> web python - < evidence/s15/deactivate_demo_admin.py"
docker compose exec -T -e SYNTH_ADMIN_USER="$SYNTH_USER" \
  web python - < "$ROOT/evidence/s15/deactivate_demo_admin.py" 2>&1 | tail -2
echo

echo "RESULT: HTTPS probe, artifact parity (two independent computations) and the browser journeys"
echo "        above. node exit=$NODE_EXIT (0 = every browser check passed)."
exit "$NODE_EXIT"
