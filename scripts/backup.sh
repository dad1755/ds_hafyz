#!/usr/bin/env bash
# AI Hub Campus — consistent SQLite backup (Sprint 12, blueprint §7 / §9 S12).
#
# What a backup contains, and why each part is there:
#   aihubcampus.db            a VACUUM INTO snapshot taken *inside* the running container. Not a
#                             file copy: the app runs in WAL mode, so `cp` of the .db alone would
#                             miss the -wal content. VACUUM INTO writes one consistent, fully
#                             checkpointed database from a read transaction, and it cannot
#                             overwrite an existing file, so a half-written snapshot is impossible.
#   model_manifest.json       the artifact the snapshot's predictions were produced by, plus
#   metrics.json              the evaluation record — a backup without these cannot be checked
#                             against what the app was actually serving.
#   dataset_metadata.json     the active dataset_versions row(s): filename, sha256, row/column
#                             counts, class balance. This is the dataset identity the restored
#                             app will claim, so it is captured next to the database, not guessed.
#   manifest.json/.txt        sha256 of every file above, the row counts, the git commit, the
#                             image id and the container start time. restore.sh refuses a backup
#                             whose checksums do not match this file.
#
# The backup is taken from the LIVE service without stopping it. Nothing is written to the
# live volume: the snapshot is built in the container's /tmp (a tmpfs under the hardened
# compose file) and streamed out with `docker exec … cat`.
#
# Why not `docker cp`: since S12 /tmp is a tmpfs, and Docker cannot copy a path that lives in a
# container's tmpfs — `docker cp <id>:/tmp/x .` fails with "Could not find the file". Reading
# the same path with `docker exec … cat` works, so the snapshot is streamed to the host and the
# container-side sha256 is compared with the host file's sha256. A stream has no size ceiling
# either, which a copy through the daemon's memory does.
#
# Usage:
#   scripts/backup.sh                      # -> backups/aihubcampus-<UTC stamp>.tar.gz
#   scripts/backup.sh --out /srv/backups   # different destination directory
#   scripts/backup.sh --keep 7             # also delete older tarballs, keeping the newest 7
#   scripts/backup.sh --help
#
# Exit codes: 0 = backup written and self-verified, 1 = check failed, 2 = bad usage/preflight.
#
# Nothing secret is read, printed or stored: credentials never enter the database file
# (only Argon2 hashes do) and the environment is never dumped.

set -euo pipefail

PROJECT="${COMPOSE_PROJECT_NAME:-aihubcampus}"
SERVICE="web"
OUT_DIR=""
KEEP=0
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
    sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

die() { printf 'backup: ERROR: %s\n' "$1" >&2; exit "${2:-1}"; }
say() { printf '%-8s %s\n' "$1" "$2"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --out)    OUT_DIR="${2:?--out needs a directory}"; shift 2 ;;
        --keep)   KEEP="${2:?--keep needs a number}"; shift 2 ;;
        --project) PROJECT="${2:?--project needs a name}"; shift 2 ;;
        --service) SERVICE="${2:?--service needs a name}"; shift 2 ;;
        -h|--help) usage ;;
        *) die "unknown argument: $1 (try --help)" 2 ;;
    esac
done

OUT_DIR="${OUT_DIR:-$REPO_ROOT/backups}"
[[ "$KEEP" =~ ^[0-9]+$ ]] || die "--keep must be a non-negative integer" 2

# --------------------------------------------------------------------------- preflight
command -v docker >/dev/null 2>&1 || die "docker is not on PATH" 2
docker info >/dev/null 2>&1 || die "cannot talk to the Docker daemon" 2

cd "$REPO_ROOT"
CID="$(docker compose -p "$PROJECT" ps -q "$SERVICE" 2>/dev/null || true)"
[[ -n "$CID" ]] || die "service '$SERVICE' is not running in compose project '$PROJECT' (start it with: docker compose up -d web)" 2

STATE="$(docker inspect --format '{{.State.Status}}' "$CID")"
[[ "$STATE" == "running" ]] || die "container $CID is '$STATE', not running" 2
HEALTH="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$CID")"
[[ "$HEALTH" == "healthy" || "$HEALTH" == "none" ]] \
    || die "container health is '$HEALTH' — refuse to snapshot an unhealthy database" 2

mkdir -p "$OUT_DIR"
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/aihubcampus-backup.XXXXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

BUNDLE="aihubcampus-$STAMP"
mkdir -p "$STAGE/$BUNDLE"
DEST="$STAGE/$BUNDLE"

say "preflight" "project=$PROJECT service=$SERVICE container=${CID:0:12} health=$HEALTH"

# --------------------------------------------------------------------------- snapshot
# Runs inside the container as the unprivileged app user. Prints one JSON object between
# sentinels so that any other stdout (a warning, a banner) cannot corrupt the parse.
SNAPSHOT_JSON="$(docker compose -p "$PROJECT" exec -T "$SERVICE" python - <<'PY'
import hashlib, json, os, sqlite3, sys

DB = os.environ.get("APP_DB_PATH", "/app/storage/aihubcampus.db")
DEST = "/tmp/aihubcampus-backup.db"

def emit(payload):
    sys.stdout.write("<<<SNAPSHOT_JSON\n" + json.dumps(payload, indent=2, sort_keys=True) + "\nSNAPSHOT_JSON>>>\n")

if not os.path.exists(DB):
    emit({"ok": False, "error": f"database not found at {DB}"}); raise SystemExit(1)

if os.path.exists(DEST):
    os.remove(DEST)

# VACUUM INTO = one consistent, checkpointed copy from a read transaction. It refuses to
# write over an existing file, which is exactly the guarantee a backup needs.
src = sqlite3.connect(DB)
src.execute("PRAGMA busy_timeout=5000")
src.execute("VACUUM INTO ?", (DEST,))
src.close()

con = sqlite3.connect(DEST)
integrity = con.execute("PRAGMA integrity_check").fetchone()[0]

tables = [r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}

def rows(sql, params=()):
    cur = con.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]

dataset = rows("SELECT * FROM dataset_versions ORDER BY id") if "dataset_versions" in tables else []
con.close()

with open(DEST, "rb") as fh:
    digest = hashlib.sha256(fh.read()).hexdigest()

emit({
    "ok": True,
    "db_path": DB,
    "snapshot_path": DEST,
    "sha256": digest,
    "bytes": os.path.getsize(DEST),
    "integrity_check": integrity,
    "journal_mode": "wal (checkpointed by VACUUM INTO)",
    "counts": counts,
    "dataset_versions": dataset,
    "sqlite_version": sqlite3.sqlite_version,
})
PY
)"

JSON="$(printf '%s\n' "$SNAPSHOT_JSON" | sed -n '/^<<<SNAPSHOT_JSON$/,/^SNAPSHOT_JSON>>>$/p' | sed '1d;$d')"
[[ -n "$JSON" ]] || die "could not read the snapshot result from the container"
printf '%s\n' "$JSON" > "$STAGE/snapshot.json"

python3 - "$STAGE/snapshot.json" <<'PY' || die "snapshot reported a failure (see above)"
import json, sys
data = json.load(open(sys.argv[1]))
if not data.get("ok"):
    print(f"  container says: {data.get('error')}", file=sys.stderr); raise SystemExit(1)
if data["integrity_check"] != "ok":
    print(f"  integrity_check = {data['integrity_check']}", file=sys.stderr); raise SystemExit(1)
PY

SHA_IN_CONTAINER="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["sha256"])' "$STAGE/snapshot.json")"
say "snapshot" "VACUUM INTO ok, integrity_check=ok, sha256=${SHA_IN_CONTAINER:0:16}…"

# --------------------------------------------------------------------------- stream out
# A failed `docker exec` exits non-zero but the shell has already created the empty host file,
# so the stream is not trusted on its exit status alone: check the bytes and the sha256 the
# container computed before the file is allowed into the bundle.
docker compose -p "$PROJECT" exec -T "$SERVICE" cat /tmp/aihubcampus-backup.db > "$DEST/aihubcampus.db" \
    || { rm -f "$DEST/aihubcampus.db"; die "could not stream the snapshot out of the container"; }
docker compose -p "$PROJECT" exec -T "$SERVICE" rm -f /tmp/aihubcampus-backup.db || true

[[ -s "$DEST/aihubcampus.db" ]] || die "the streamed snapshot is empty — the backup is not usable"

SHA_ON_HOST="$(sha256sum "$DEST/aihubcampus.db" | cut -d' ' -f1)"
[[ "$SHA_IN_CONTAINER" == "$SHA_ON_HOST" ]] \
    || die "checksum changed in transit: container=$SHA_IN_CONTAINER host=$SHA_ON_HOST"
say "copy" "streamed docker exec cat, verified — host checksum equals the container's ($SHA_ON_HOST)"

python3 -c 'import json,sys;print(json.dumps(json.load(open(sys.argv[1]))["dataset_versions"], indent=2, sort_keys=True))' \
    "$STAGE/snapshot.json" > "$DEST/dataset_metadata.json"

# The model the snapshot was served by. Read from the running container, not from the repo:
# a checkout could be ahead of what is actually deployed.
for f in model_manifest.json metrics.json; do
    docker cp "$CID:/app/models/$f" "$DEST/$f" >/dev/null || die "cannot read /app/models/$f from the container"
done
ARTIFACT_SHA="$(docker compose -p "$PROJECT" exec -T "$SERVICE" python -c '
import hashlib, sys
try:
    print(hashlib.sha256(open("/app/models/best_pipeline.joblib","rb").read()).hexdigest())
except OSError:
    print("unavailable")
' | tr -d '\r')"
say "model" "manifest + metrics copied, artifact sha256=${ARTIFACT_SHA:0:16}…"

# --------------------------------------------------------------------------- manifest
GIT_COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo "not-a-git-checkout")"
GIT_BRANCH="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "-")"
IMAGE_ID="$(docker inspect --format '{{.Image}}' "$CID")"
IMAGE_REF="$(docker inspect --format '{{.Config.Image}}' "$CID")"
STARTED="$(docker inspect --format '{{.State.StartedAt}}' "$CID")"
HOSTNAME_="$(hostname -f 2>/dev/null || hostname)"

python3 - "$DEST" "$STAGE/snapshot.json" "$GIT_COMMIT" "$GIT_BRANCH" "$IMAGE_ID" "$IMAGE_REF" "$STARTED" "$ARTIFACT_SHA" "$PROJECT" "$SERVICE" <<'PY'
import hashlib, json, os, sys
from datetime import datetime, timezone

dest, snap_path, commit, branch, image_id, image_ref, started, artifact_sha, project, service = sys.argv[1:11]
snap = json.load(open(snap_path))

files = {}
for name in sorted(os.listdir(dest)):
    path = os.path.join(dest, name)
    if not os.path.isfile(path):
        continue
    with open(path, "rb") as fh:
        blob = fh.read()
    files[name] = {"sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)}

manifest = {
    "format": "aihubcampus-backup/1",
    "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "compose": {"project": project, "service": service},
    "source": {"git_commit": commit, "git_branch": branch,
               "image_id": image_id, "image_ref": image_ref,
               "container_started_at": started},
    "database": {"path_in_container": snap["db_path"],
                 "snapshot_method": "sqlite VACUUM INTO (consistent, WAL-safe)",
                 "integrity_check": snap["integrity_check"],
                 "sqlite_version": snap["sqlite_version"],
                 "sha256": snap["sha256"], "bytes": snap["bytes"]},
    "row_counts": snap["counts"],
    "model": {"artifact_sha256": artifact_sha},
    "files": files,
}
with open(os.path.join(dest, "manifest.json"), "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2, sort_keys=True)
    fh.write("\n")

lines = [
    f"AI Hub Campus backup — {manifest['created_utc']}",
    "",
    f"compose project   : {project} / {service}",
    f"git               : {commit} ({branch})",
    f"image             : {image_ref} ({image_id[:19]}…)",
    f"container started : {started}",
    "",
    "database",
    f"  snapshot method : {manifest['database']['snapshot_method']}",
    f"  integrity_check : {manifest['database']['integrity_check']}",
    f"  sqlite          : {manifest['database']['sqlite_version']}",
    f"  sha256          : {manifest['database']['sha256']}",
    f"  bytes           : {manifest['database']['bytes']}",
    "",
    "row counts at snapshot time",
]
for table, count in sorted(snap["counts"].items()):
    lines.append(f"  {table:<20} {count}")
lines += ["", f"model artifact sha256 : {artifact_sha}", "", "files"]
for name, meta in files.items():
    lines.append(f"  {name:<24} {meta['sha256']}  {meta['bytes']} B")
lines += ["", "Restore with: scripts/restore.sh --backup <this tarball> --to-dir <empty dir>",
          "Never restore over the live volume without reading docs/runbook.md §5."]
with open(os.path.join(dest, "MANIFEST.txt"), "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")
PY

# --------------------------------------------------------------------------- pack
TARBALL="$OUT_DIR/$BUNDLE.tar.gz"
tar -C "$STAGE" -czf "$TARBALL" "$BUNDLE"
( cd "$OUT_DIR" && sha256sum "$BUNDLE.tar.gz" > "$BUNDLE.tar.gz.sha256" )
say "packed" "$TARBALL ($(du -h "$TARBALL" | cut -f1)), checksum written beside it"

# --------------------------------------------------------------------------- self-verify
# Read the tarball back and compare every file against manifest.json. A backup that cannot be
# read is not a backup, so this happens now and not on the day it is needed.
VERIFY="$(mktemp -d "${TMPDIR:-/tmp}/aihubcampus-verify.XXXXXXXX")"
tar -C "$VERIFY" -xzf "$TARBALL"
if python3 - "$VERIFY/$BUNDLE" <<'PY'
import hashlib, json, os, sqlite3, sys
root = sys.argv[1]
manifest = json.load(open(os.path.join(root, "manifest.json")))
problems = []
for name, meta in manifest["files"].items():
    path = os.path.join(root, name)
    if not os.path.isfile(path):
        problems.append(f"missing {name}"); continue
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if digest != meta["sha256"]:
        problems.append(f"{name}: sha256 {digest} != manifest {meta['sha256']}")
con = sqlite3.connect(os.path.join(root, "aihubcampus.db"))
integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
if integrity != "ok":
    problems.append(f"integrity_check on the extracted copy: {integrity}")
counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
          for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
for table, expected in manifest["row_counts"].items():
    if counts.get(table) != expected:
        problems.append(f"{table}: extracted {counts.get(table)} != manifest {expected}")
con.close()
if problems:
    print("FAIL — the backup does not verify against its own manifest:")
    for p in problems:
        print(f"  - {p}")
    raise SystemExit(1)
print(f"PASS — {len(manifest['files'])} file(s) match the manifest, integrity_check=ok, "
      f"{len(manifest['row_counts'])} table count(s) match")
PY
then
    VERIFY_RC=0
else
    VERIFY_RC=1
fi
rm -rf "$VERIFY"
[[ $VERIFY_RC -eq 0 ]] || die "self-verification of $TARBALL failed"

# --------------------------------------------------------------------------- retention
if [[ "$KEEP" -gt 0 ]]; then
    mapfile -t OLD < <(ls -1t "$OUT_DIR"/aihubcampus-*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) || true)
    for f in "${OLD[@]:-}"; do
        [[ -n "$f" ]] || continue
        rm -f "$f" "$f.sha256"
        say "prune" "removed $(basename "$f")"
    done
fi

say "done" "$TARBALL"
printf '\nNext: scripts/restore.sh --backup %s --to-dir /tmp/restore-check\n' "$TARBALL"
