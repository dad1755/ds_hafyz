#!/usr/bin/env bash
# S9 UI check driver.
#
# Starts a throwaway container of the freshly built image (its own storage volume, its own
# synthetic administrator), drives it with a real Chromium from the Playwright image, then
# removes everything it created. The deployment's own database is never written to.
#
#   bash evidence/s9/run_ui_check.sh > evidence/s9/browser_check.txt 2>&1
#
# Credentials are generated per run and never printed.
set -uo pipefail
cd /home/ec-user/non_prod/hafyz_ds

ROOT="$PWD"
OUT="$ROOT/evidence/s9"
FIXTURES="$OUT/fixtures"
CONTAINER="aihubcampus-s9-ui"
VOLUME="aihubcampus-s9-ui-storage"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1
  docker volume rm "$VOLUME" >/dev/null 2>&1
}
trap cleanup EXIT

mkdir -p "$FIXTURES"

# --- fixtures: subsets of the seed, and one upload with a column removed ---------------
python3 - "$ROOT/data/UCI_Credit_Card.csv" "$FIXTURES" <<'PY'
import csv
import sys
from pathlib import Path

seed, out = Path(sys.argv[1]), Path(sys.argv[2])
with seed.open(newline="", encoding="utf-8-sig") as handle:
    reader = csv.reader(handle)
    header = next(reader)
    rows = list(reader)

def write(name, records, columns):
    keep = [index for index, column in enumerate(header) if column in columns]
    with (out / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([header[index] for index in keep])
        for record in records:
            writer.writerow([record[index] for index in keep])

write("stage_valid.csv", rows[:400], set(header))
write("stage_second.csv", rows[400:900], set(header))
write("stage_missing_column.csv", rows[:30], set(header) - {"PAY_6"})
print("fixtures written:", sorted(p.name for p in out.glob("*.csv")))
PY

# --- throwaway deployment ---------------------------------------------------------------
ADMIN_USER="s9_browser_admin"
ADMIN_PASSWORD="$(openssl rand -hex 14)"

docker volume create "$VOLUME" >/dev/null
docker run -d --name "$CONTAINER" \
  --network aihubcampus_internal \
  -v "$VOLUME:/app/storage" \
  -v "$ROOT/data/UCI_Credit_Card.csv:/app/data/UCI_Credit_Card.csv:ro,z" \
  -e APP_DB_PATH=/app/storage/aihubcampus.db \
  -e APP_QUARANTINE_DIR=/app/storage/quarantine \
  -e INITIAL_ADMIN_USERNAME="$ADMIN_USER" \
  -e INITIAL_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  aihubcampus-web:s9 >/dev/null

echo "throwaway container: $CONTAINER (volume $VOLUME, synthetic administrator, no secrets shown)"

for _ in $(seq 1 40); do
  if docker exec "$CONTAINER" python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:2026/_stcore/health', timeout=2)" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

docker exec -e INITIAL_ADMIN_USERNAME="$ADMIN_USER" \
            -e INITIAL_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
       "$CONTAINER" python scripts/init_admin.py 2>&1 | tail -3

echo
echo "\$ docker run --rm --network aihubcampus_internal -v \"\$PWD/evidence/s9:/work:z\" -w /work \\"
echo "    -v <playwright modules>:/pw/node_modules:ro -e NODE_PATH=/pw/node_modules \\"
echo "    -e SYNTH_ADMIN_USER=<synthetic> -e SYNTH_ADMIN_PASSWORD=<synthetic> \\"
echo "    mcr.microsoft.com/playwright:v1.55.0-noble node ui_datasets.js $CONTAINER 2026"
# The Playwright image ships browsers but not the npm package, so it is installed once into a
# scratch directory outside this repository and mounted read-only at run time. The mounts carry
# `z` because SELinux on this host denies a container write access to an unlabelled home path.
PW_CACHE="${PW_CACHE:-$HOME/.cache/s9-playwright}"
mkdir -p "$PW_CACHE"
docker run --rm -v "$PW_CACHE:/pw:z" -w /pw mcr.microsoft.com/playwright:v1.55.0-noble \
  npm install --no-audit --no-fund --silent playwright@1.55.0 >/dev/null

docker run --rm --network aihubcampus_internal \
  -v "$OUT:/work:z" -w /work \
  -v "$PW_CACHE:/pw:ro,z" \
  -e NODE_PATH=/pw/node_modules \
  -e SYNTH_ADMIN_USER="$ADMIN_USER" \
  -e SYNTH_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  -e VALID_CSV=/work/fixtures/stage_valid.csv \
  -e SECOND_CSV=/work/fixtures/stage_second.csv \
  -e BAD_CSV=/work/fixtures/stage_missing_column.csv \
  mcr.microsoft.com/playwright:v1.55.0-noble \
  node ui_datasets.js "$CONTAINER" 2026
echo "exit=$?"

echo
echo "\$ docker exec $CONTAINER sha256sum /app/models/best_pipeline.joblib"
docker exec "$CONTAINER" sha256sum /app/models/best_pipeline.joblib

echo
echo "\$ docker exec -i $CONTAINER python -c '<dataset_versions after the browser run>'"
docker exec -i "$CONTAINER" python - <<'PY'
import sqlite3
conn = sqlite3.connect('/app/storage/aihubcampus.db')
conn.row_factory = sqlite3.Row
for row in conn.execute(
    "SELECT id, record_count, class_zero, class_one, is_active, status FROM dataset_versions ORDER BY id"
):
    print(dict(row))
print("active rows =", conn.execute(
    "SELECT COUNT(*) FROM dataset_versions WHERE is_active = 1").fetchone()[0])
for row in conn.execute("SELECT error_codes, reason FROM dataset_rejections ORDER BY id"):
    print("rejection:", dict(row))
PY

rm -rf "$FIXTURES"
