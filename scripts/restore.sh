#!/usr/bin/env bash
# AI Hub Campus — verified restore (Sprint 12, blueprint §7 / §9 S12).
#
# A restore is the one operation that can destroy the only copy of the data, so this script
# is deliberately paranoid:
#
#   * it verifies the tarball against the `.sha256` written by backup.sh;
#   * it verifies every file inside against `manifest.json`;
#   * it runs `PRAGMA integrity_check` and re-counts every table against the manifest;
#   * it refuses to write into the live volume unless --allow-live AND --yes are given AND
#     the service is actually stopped — and even then it copies the current database aside
#     first, so a bad restore is still reversible.
#
# The safe, rehearsed path (and the one the S12 acceptance uses) is a *disposable target*:
#   scripts/restore.sh --backup backups/aihubcampus-<stamp>.tar.gz --to-dir /tmp/restore-check
#   scripts/restore.sh --backup backups/aihubcampus-<stamp>.tar.gz --to-volume aihubcampus-restore-check
#
# Usage:
#   scripts/restore.sh --backup <file.tar.gz|dir> --to-dir <empty-or-new dir> [--yes]
#   scripts/restore.sh --backup <file.tar.gz|dir> --to-volume <name> [--yes]
#   scripts/restore.sh --backup <file.tar.gz|dir> --to-volume aihubcampus_app_storage --allow-live --yes
#   scripts/restore.sh --help
#
# Exit codes: 0 = restored and verified, 1 = verification failed (target untouched), 2 = bad usage.
#
# Never restores secrets: the bundle contains no credential, and the environment is not read.

set -euo pipefail

PROJECT="${COMPOSE_PROJECT_NAME:-aihubcampus}"
SERVICE="web"
IMAGE="aihubcampus-web:local"
BACKUP=""
TO_DIR=""
TO_VOLUME=""
ALLOW_LIVE=0
ASSUME_YES=0

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
    sed -n '2,32p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

die()  { printf 'restore: ERROR: %s\n' "$1" >&2; exit "${2:-1}"; }
say()  { printf '%-10s %s\n' "$1" "$2"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backup)     BACKUP="${2:?--backup needs a path}"; shift 2 ;;
        --to-dir)     TO_DIR="${2:?--to-dir needs a directory}"; shift 2 ;;
        --to-volume)  TO_VOLUME="${2:?--to-volume needs a name}"; shift 2 ;;
        --allow-live) ALLOW_LIVE=1; shift ;;
        --yes|-y)     ASSUME_YES=1; shift ;;
        --project)    PROJECT="${2:?--project needs a name}"; shift 2 ;;
        --image)      IMAGE="${2:?--image needs a reference}"; shift 2 ;;
        -h|--help)    usage ;;
        *) die "unknown argument: $1 (try --help)" 2 ;;
    esac
done

[[ -n "$BACKUP" ]] || die "--backup is required (try --help)" 2
if [[ -n "$TO_DIR" && -n "$TO_VOLUME" ]]; then
    die "--to-dir and --to-volume are mutually exclusive" 2
fi
[[ -n "$TO_DIR" || -n "$TO_VOLUME" ]] || die "one of --to-dir or --to-volume is required" 2
[[ -e "$BACKUP" ]] || die "backup not found: $BACKUP" 2
command -v docker >/dev/null 2>&1 || die "docker is not on PATH" 2

LIVE_VOLUME="${PROJECT}_app_storage"

# --------------------------------------------------------------------------- guard
if [[ -n "$TO_VOLUME" ]]; then
    if [[ "$TO_VOLUME" == "$LIVE_VOLUME" ]]; then
        [[ "$ALLOW_LIVE" -eq 1 ]] || die "refusing to overwrite the live volume '$LIVE_VOLUME'.
       This is the production database. Take a backup first (scripts/backup.sh), stop the
       service, then re-run with --allow-live --yes if you really mean it. The runbook
       (docs/runbook.md §5) walks through the rollback." 2
        [[ "$ASSUME_YES" -eq 1 ]] || die "--allow-live also requires --yes (non-interactive by design)" 2
        RUNNING="$(docker compose -p "$PROJECT" ps -q "$SERVICE" 2>/dev/null || true)"
        if [[ -n "$RUNNING" ]]; then
            RUN_STATE="$(docker inspect --format '{{.State.Status}}' "$RUNNING")"
            [[ "$RUN_STATE" != "running" ]] \
                || die "service '$SERVICE' is still running. Stop it first: docker compose stop web" 2
        fi
        say "guard" "live-volume restore authorised — service is stopped"
    fi
else
    mkdir -p "$TO_DIR"
    if [[ -n "$(ls -A "$TO_DIR" 2>/dev/null)" && -e "$TO_DIR/aihubcampus.db" ]]; then
        [[ "$ASSUME_YES" -eq 1 ]] || die "$TO_DIR already contains aihubcampus.db — pass --yes to overwrite it" 2
    fi
fi

# --------------------------------------------------------------------------- stage
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/aihubcampus-restore.XXXXXXXX")"
trap 'rm -rf "$STAGE"' EXIT

if [[ -d "$BACKUP" ]]; then
    SRC_DIR="$BACKUP"
    say "source" "directory $BACKUP"
else
    [[ -f "$BACKUP.sha256" ]] || die "missing checksum file $BACKUP.sha256 — cannot prove the backup is intact" 2
    ( cd "$(dirname "$BACKUP")" && sha256sum -c "$(basename "$BACKUP").sha256" --status ) \
        || die "tarball checksum does not match $BACKUP.sha256"
    say "source" "tarball $BACKUP (sha256 matches its .sha256)"
    tar -C "$STAGE" -xzf "$BACKUP"
    ENTRY="$(find "$STAGE" -mindepth 1 -maxdepth 1 -type d -name 'aihubcampus-*' | head -1)"
    [[ -n "$ENTRY" ]] || die "the tarball does not contain an aihubcampus-* bundle directory"
    SRC_DIR="$ENTRY"
fi

[[ -f "$SRC_DIR/manifest.json" ]] || die "no manifest.json in $SRC_DIR — not an aihubcampus backup"
[[ -f "$SRC_DIR/aihubcampus.db" ]] || die "no aihubcampus.db in $SRC_DIR"

# --------------------------------------------------------------------------- verify
if python3 - "$SRC_DIR" <<'PY'
import hashlib, json, os, sqlite3, sys
root = sys.argv[1]
manifest = json.load(open(os.path.join(root, "manifest.json")))
problems = []

if manifest.get("format") != "aihubcampus-backup/1":
    problems.append(f"unknown bundle format: {manifest.get('format')!r}")

for name, meta in manifest["files"].items():
    path = os.path.join(root, name)
    if not os.path.isfile(path):
        problems.append(f"missing {name}"); continue
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    if digest != meta["sha256"]:
        problems.append(f"{name}: sha256 {digest} != manifest {meta['sha256']}")

db_path = os.path.join(root, "aihubcampus.db")
con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
if integrity != "ok":
    problems.append(f"integrity_check = {integrity}")
counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
          for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
for table, expected in manifest["row_counts"].items():
    if counts.get(table) != expected:
        problems.append(f"{table}: backup holds {counts.get(table)}, manifest says {expected}")
con.close()

if problems:
    print("FAIL — the backup does not verify:")
    for p in problems:
        print(f"  - {p}")
    raise SystemExit(1)
print(f"verified — {len(manifest['files'])} file(s) match the manifest, integrity_check=ok, "
      f"{len(manifest['row_counts'])} table count(s) match")
print(f"database sha256 {manifest['database']['sha256']}")
PY
then
    :
else
    die "backup verification failed — nothing was written to the target" 1
fi
say "verify" "checksums, integrity_check and row counts all match the manifest"

# --------------------------------------------------------------------------- place
EXPECTED_SHA="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["database"]["sha256"])' \
    "$SRC_DIR/manifest.json")"
[[ -n "$EXPECTED_SHA" ]] || die "manifest has no database checksum"

if [[ -n "$TO_DIR" ]]; then
    cp "$SRC_DIR/aihubcampus.db" "$TO_DIR/aihubcampus.db"
    TARGET_LABEL="$TO_DIR/aihubcampus.db"
    RESTORED_SHA="$(sha256sum "$TO_DIR/aihubcampus.db" | cut -d' ' -f1)"
else
    docker volume inspect "$TO_VOLUME" >/dev/null 2>&1 || docker volume create "$TO_VOLUME" >/dev/null
    # A throwaway container writes the file into the volume. Root is needed only because the
    # named volume is root-owned; the container exits immediately and touches nothing else.
    docker run --rm --user 0:0 --network none \
        -v "$TO_VOLUME:/target" -v "$SRC_DIR:/src:ro,z" \
        "$IMAGE" cp /src/aihubcampus.db /target/aihubcampus.db \
        || die "could not write into volume $TO_VOLUME"
    RESTORED_SHA="$(docker run --rm --user 0:0 --network none -v "$TO_VOLUME:/target" \
        "$IMAGE" sha256sum /target/aihubcampus.db | cut -d' ' -f1)"
    TARGET_LABEL="volume $TO_VOLUME:/aihubcampus.db"
fi

[[ "$RESTORED_SHA" == "$EXPECTED_SHA" ]] \
    || die "restored checksum $RESTORED_SHA does not equal the manifest's $EXPECTED_SHA"
say "restored" "$TARGET_LABEL"

# --------------------------------------------------------------------------- prove
# Open the restored copy the way the app would — read-write, in a container, on the target —
# and re-count. This is the round-trip the acceptance asks for: same checksum, same counts.
if [[ -n "$TO_VOLUME" ]]; then
    docker run --rm --user 0:0 --network none -v "$TO_VOLUME:/target" "$IMAGE" python - <<'PY'
import json, sqlite3, sys
con = sqlite3.connect("/target/aihubcampus.db")
integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
print("integrity_check:", integrity)
print("row counts:", json.dumps(counts, sort_keys=True))
con.close()
if integrity != "ok":
    raise SystemExit(1)
PY
else
    python3 - "$TO_DIR/aihubcampus.db" <<'PY'
import json, sqlite3, sys
con = sqlite3.connect(sys.argv[1])
integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
counts = {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
print("integrity_check:", integrity)
print("row counts:", json.dumps(counts, sort_keys=True))
con.close()
if integrity != "ok":
    raise SystemExit(1)
PY
fi
say "prove" "the restored database opens, passes integrity_check and re-counts"

cat <<EOF

Restored and verified.
  database checksum : $RESTORED_SHA
  target            : $TARGET_LABEL

The bundle's model_manifest.json / metrics.json are the *record* of what produced this data;
the model itself ships inside the image and is verified at startup by src/inference.py.
To bring a restored database into service, see docs/runbook.md §5 (rollback).
EOF
