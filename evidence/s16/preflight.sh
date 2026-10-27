#!/usr/bin/env bash
# S16 pre-flight — what is actually deployed, and is it this tree?
#
#   bash evidence/s16/preflight.sh > evidence/s16/preflight.txt 2>&1
#
# Answers four questions before any release action is taken:
#   1. which commit is under test, and is the tree clean?
#   2. which container/image is serving right now, and since when?
#   3. is the running image built from THIS tree? (per-file sha256 of every application
#      .py file inside the image, against the same file on disk — the only honest way to
#      say "the deployment matches the release" without trusting a build log)
#   4. does the live database match the artifact the manifest claims?
#
# Read-only: no container is started, stopped, written to or reconfigured. No secret is read,
# printed or hashed.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2

PROJECT="${COMPOSE_PROJECT_NAME:-aihubcampus}"
SERVICE=web
IMAGE=aihubcampus-web:local
CONTAINER="$(docker compose ps -q "$SERVICE" 2>/dev/null | head -1)"

echo "# S16 pre-flight — the deployed state, and whether it is this tree"
echo "# run (UTC):   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "# host:        $(hostname) · $(uname -r)"
echo "# repo:        $PWD"
echo "# compose:     project=$PROJECT service=$SERVICE"
echo

echo "=== 1. the tree under test ==="
echo "\$ git rev-parse --short HEAD · branch · status"
printf 'HEAD      : %s\n' "$(git rev-parse HEAD)"
printf 'short     : %s\n' "$(git rev-parse --short HEAD)"
printf 'branch    : %s\n' "$(git rev-parse --abbrev-ref HEAD)"
printf 'tags      : %s\n' "$(git tag --points-at HEAD | paste -sd, - | sed 's/^$/none/')"
printf 'status    :\n'
git status --short | sed 's/^/            /'
if [[ -z "$(git status --porcelain)" ]]; then echo '            (clean)'; fi
echo

echo "=== 2. what is serving ==="
echo "\$ docker compose ps"
docker compose ps --format 'table {{.Service}}\t{{.Name}}\t{{.Status}}\t{{.Ports}}'
echo
if [[ -n "$CONTAINER" ]]; then
  echo "\$ docker inspect $CONTAINER"
  docker inspect "$CONTAINER" --format 'container   : {{.Name}} ({{.Id}})
image       : {{.Image}}
started     : {{.State.StartedAt}}
health      : {{.State.Health.Status}}
restart     : {{.HostConfig.RestartPolicy.Name}}
read_only   : {{.HostConfig.ReadonlyRootfs}}
cap_drop    : {{.HostConfig.CapDrop}}
ports       : {{.HostConfig.PortBindings}}'
  echo
  echo "\$ docker port $CONTAINER   (empty means nothing is published on the host)"
  docker port "$CONTAINER" || true
  echo
fi
echo "\$ docker image inspect $IMAGE"
docker image inspect "$IMAGE" --format 'image id    : {{.Id}}
created     : {{.Created}}
repo tags   : {{.RepoTags}}'
echo

echo "=== 3. is the running image built from this tree? ==="
echo "# sha256 of every application .py file, inside the image vs on disk"
docker run --rm --network none "$IMAGE" python -c '
import hashlib, pathlib
root = pathlib.Path("/app")
for p in sorted(root.rglob("*.py")):
    print(hashlib.sha256(p.read_bytes()).hexdigest(), p.relative_to(root))
' > /tmp/s16_image_files.txt 2>/dev/null || { echo "FAIL could not read the image filesystem"; exit 1; }
python3 - "$PWD" <<'PY' > /tmp/s16_tree_files.txt
import hashlib, pathlib, sys
root = pathlib.Path(sys.argv[1])
for p in sorted(root.rglob("*.py")):
    rel = p.relative_to(root).as_posix()
    if "__pycache__" in rel or rel.startswith(("evidence/", "tests/")):
        continue
    print(hashlib.sha256(p.read_bytes()).hexdigest(), rel)
PY
if diff -u /tmp/s16_image_files.txt /tmp/s16_tree_files.txt > /tmp/s16_code_diff.txt; then
  echo "PASS  the image's application code is byte-identical to the working tree"
  echo "      $(wc -l < /tmp/s16_image_files.txt) .py files compared, 0 differ"
else
  echo "FAIL  the image and the tree differ:"
  sed 's/^/      /' /tmp/s16_code_diff.txt
fi
echo
echo "# the model artifact and its manifest, as the image ships them"
docker run --rm --network none "$IMAGE" python -c '
import hashlib, json, pathlib
m = pathlib.Path("/app/models")
art = m / "best_pipeline.joblib"
print("image best_pipeline.joblib sha256:", hashlib.sha256(art.read_bytes()).hexdigest())
print("image model_manifest.json  sha256:", hashlib.sha256((m / "model_manifest.json").read_bytes()).hexdigest())
' 2>/dev/null
echo "tree  best_pipeline.joblib sha256: $(sha256sum models/best_pipeline.joblib | cut -d' ' -f1)"
echo "tree  model_manifest.json  sha256: $(sha256sum models/model_manifest.json | cut -d' ' -f1)"
echo

echo "=== 4. the live database, as it stands ==="
if [[ -n "$CONTAINER" ]]; then
  echo "\$ docker compose exec -T web python - <<'PY'  (read-only: file sha256 + row counts)"
  docker compose exec -T "$SERVICE" python - <<'PY'
import hashlib, json, sqlite3, pathlib
db = pathlib.Path("/app/storage/aihubcampus.db")
print("live db sha256 :", hashlib.sha256(db.read_bytes()).hexdigest())
print("live db bytes  :", db.stat().st_size)
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
tables = [r[0] for r in con.execute(
    "select name from sqlite_master where type='table' order by name")]
counts = {t: con.execute(f'select count(*) from "{t}"').fetchone()[0] for t in tables}
print("live row counts:", json.dumps(counts, sort_keys=True))
print("schema version :", con.execute("select max(version) from schema_migrations").fetchone()[0])
for row in con.execute(
        "select id, original_filename_safe, record_count, column_count, sha256, is_active, status "
        "from dataset_versions order by id"):
    print("dataset version:", row)
con.close()
PY
else
  echo "FAIL  no running $SERVICE container — there is nothing to release"
fi
echo
echo "=== 5. the release gate script is present and executable ==="
for s in verify_release.sh smoke_test.sh backup.sh restore.sh; do
  if [[ -x "scripts/$s" ]]; then echo "PASS  scripts/$s executable"; else echo "FAIL  scripts/$s missing or not executable"; fi
done
