#!/usr/bin/env bash
# S12 evidence — a fresh clone of the branch, plus the two operator-supplied files, builds and
# serves. This is the "does the repo alone contain everything" test: nothing is taken from the
# working checkout except the two git-ignored inputs the operator owns (the CSV and .env).
#
# Stream isolation: this does NOT create a second Compose project. A second project on this
# host would collide with the live `aihubcampus` stack's network and volume namespace, so the
# clone is built with `docker build` and run with `docker run --network none`, publishing no
# port. The health probe therefore runs *inside* the container.
#
# Run from the repo root:  bash evidence/s12/fresh_clone.sh 2>&1 | tee evidence/s12/fresh_clone.txt
set -uo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
IMAGE="aihubcampus-web:s12-fresh"
VOLUME="aihubcampus-s12-fresh-storage"
NAME="aihubcampus-s12-fresh-probe"
WORK="$(mktemp -d /tmp/s12-fresh-XXXXXX)"
CLONE="$WORK/clone"

cleanup() {
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    rm -rf "$WORK"
}
trap cleanup EXIT

# A previous interrupted run can leave a probe container behind holding the volume; remove it
# by name before starting so the teardown at the end is unconditional.
docker rm -f "$NAME" >/dev/null 2>&1 || true

echo "AI Hub Campus S12 — fresh clone build and run — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

echo "=== git clone (local, branch $BRANCH) ==="
git clone --quiet --branch "$BRANCH" "$REPO_ROOT" "$CLONE" || { echo "clone FAILED"; exit 1; }
git -C "$CLONE" log --oneline -1
echo "(the two untracked entries are the CSV and .env the operator supplies — neither is in git)"
git -C "$CLONE" status --porcelain
echo

echo "=== the dataset the operator supplies ==="
cp "$REPO_ROOT/data/UCI_Credit_Card.csv" "$CLONE/data/UCI_Credit_Card.csv"
cp "$REPO_ROOT/.env" "$CLONE/.env"
echo "rows (incl header): $(wc -l < "$CLONE/data/UCI_Credit_Card.csv")"
echo "bytes: $(stat -c %s "$CLONE/data/UCI_Credit_Card.csv")"
echo

echo "=== compose contract validates on the clone ==="
( cd "$CLONE" && docker compose config --quiet ) && echo "docker compose config --quiet -> exit 0"
echo

echo "=== docker build (fresh clone, no compose project created) ==="
BUILD_LOG="$WORK/build.log"
( cd "$CLONE" && docker build -t "$IMAGE" . >"$BUILD_LOG" 2>&1 )
BUILD_RC=$?
grep -E '^(#[0-9]+ (exporting|naming|DONE)|ERROR)' "$BUILD_LOG" | tail -12
if [[ $BUILD_RC -ne 0 ]]; then
    echo "docker build FAILED (exit $BUILD_RC)"
    tail -25 "$BUILD_LOG"
    exit 1
fi
echo "docker build -> exit 0"
echo

echo "=== image ==="
IMG_ID="$(docker image inspect --format '{{.Id}}' "$IMAGE")"
echo "image id  : $IMG_ID"
echo "created   : $(docker image inspect --format '{{.Created}}' "$IMAGE")"
echo "user      : $(docker image inspect --format '{{.Config.User}}' "$IMAGE")"
echo "size      : $(docker image inspect --format '{{.Size}}' "$IMAGE") bytes"
echo "env (no secret expected): $(docker image inspect --format '{{json .Config.Env}}' "$IMAGE")"
echo

echo "=== docker run — no network, no published port, read-only rootfs, caps dropped ==="
docker volume create "$VOLUME" >/dev/null
CID="$(docker run -d --name "$NAME" \
    --network none \
    --read-only \
    --tmpfs /tmp:rw,noexec,nosuid,size=256m \
    --tmpfs /home/app/.cache:rw,noexec,nosuid,size=64m \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    --env-file "$CLONE/.env" \
    -e APP_DB_PATH=/app/storage/aihubcampus.db \
    -e APP_PORT=2026 \
    -e APP_QUARANTINE_DIR=/app/storage/quarantine \
    -v "$VOLUME":/app/storage \
    -v "$CLONE/data/UCI_Credit_Card.csv":/app/data/UCI_Credit_Card.csv:ro,z \
    "$IMAGE")"
echo "$CID"
echo

echo "=== wait for the health probe (not a fixed sleep) ==="
ok=0
for i in $(seq 1 30); do
    sleep 2
    if docker exec "$CID" python -c \
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:2026/_stcore/health', timeout=3)" 2>/dev/null; then
        echo "poll $i: healthy"
        ok=1
        break
    fi
    echo "poll $i: starting"
done
[[ $ok -eq 1 ]] || { echo "health probe FAILED"; docker logs "$CID" 2>&1 | tail -20; exit 1; }
echo

echo "=== the fresh container serves ==="
docker exec -i "$CID" python - <<'PY'
import urllib.request
r = urllib.request.urlopen("http://127.0.0.1:2026/_stcore/health", timeout=5)
print("GET /_stcore/health ->", r.status, r.read().decode().strip())
r = urllib.request.urlopen("http://127.0.0.1:2026/", timeout=10)
body = r.read()
print("GET /               ->", r.status, "html", len(body), "bytes")
PY
echo

echo "=== and it is the hardened runtime ==="
echo "uid            : $(docker exec "$CID" id -u) ($(docker exec "$CID" id -un))"
echo "read_only      : $(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$CID")"
echo "cap_drop       : $(docker inspect --format '{{json .HostConfig.CapDrop}}' "$CID")"
echo "port bindings  : $(docker inspect --format '{{json .HostConfig.PortBindings}}' "$CID")"
echo "docker port    : '$(docker port "$CID" 2>/dev/null)'"
echo

echo "=== the artifact verifies inside the fresh container ==="
docker exec "$CID" python ml/verify_artifact.py 2>&1 | tr -d '\r'
echo

echo "=== logs (startup, no credential) ==="
docker logs "$CID" 2>&1 | grep -vE 'password|token|secret' | head -20
echo

echo "=== the probe container is torn down; the live stack is untouched ==="
docker rm -f "$CID" >/dev/null
docker volume rm "$VOLUME" >/dev/null
echo "done"
