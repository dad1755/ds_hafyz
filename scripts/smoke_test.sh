#!/usr/bin/env bash
# AI Hub Campus — smoke test (Sprint 12, blueprint §7 operator checklist).
#
# Answers one question, in about ten seconds, without opening a browser: is the stack that is
# running right now the hardened stack this project claims to ship, and is it serving?
#
# Every check reads the live container (`docker inspect`, `docker exec`) — never a file in the
# repo — so a passing run describes the deployment, not the checkout. Nothing is published on
# a host port, so the probes run *inside* the container.
#
# Usage:
#   scripts/smoke_test.sh                          # local stack (compose project aihubcampus)
#   scripts/smoke_test.sh --url https://www.aihubcampus.online   # + the public HTTPS surface (S13)
#   scripts/smoke_test.sh --project aihubcampus --service web
#   scripts/smoke_test.sh --help
#
# Exit codes: 0 = every check passed, 1 = at least one FAIL, 2 = the stack is not there to test.
#
# Prints no secret: it never dumps the environment, the .env file or a credential.

set -uo pipefail   # deliberately not -e: a failing check must be recorded, not abort the run.

PROJECT="${COMPOSE_PROJECT_NAME:-aihubcampus}"
SERVICE="web"
PUBLIC_URL=""
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

PASS=0
FAIL=0
SKIP=0
FAILED_NAMES=()

usage() {
    sed -n '2,22p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --url)     PUBLIC_URL="${2:?--url needs an https URL}"; shift 2 ;;
        --project) PROJECT="${2:?--project needs a name}"; shift 2 ;;
        --service) SERVICE="${2:?--service needs a name}"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "smoke_test: unknown argument: $1 (try --help)" >&2; exit 2 ;;
    esac
done

ok()   { PASS=$((PASS + 1)); printf 'PASS  %-34s %s\n' "$1" "${2:-}"; }
bad()  { FAIL=$((FAIL + 1)); FAILED_NAMES+=("$1"); printf 'FAIL  %-34s %s\n' "$1" "${2:-}"; }
skip() { SKIP=$((SKIP + 1)); printf 'SKIP  %-34s %s\n' "$1" "${2:-}"; }

command -v docker >/dev/null 2>&1 || { echo "smoke_test: docker is not on PATH" >&2; exit 2; }
cd "$REPO_ROOT" || exit 2

CID="$(docker compose -p "$PROJECT" ps -q "$SERVICE" 2>/dev/null || true)"
if [[ -z "$CID" ]]; then
    echo "smoke_test: no running '$SERVICE' container in compose project '$PROJECT'." >&2
    echo "            start it with: docker compose up -d web" >&2
    exit 2
fi
SHORT="${CID:0:12}"

printf 'AI Hub Campus smoke test — %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'project=%s service=%s container=%s\n\n' "$PROJECT" "$SERVICE" "$SHORT"

# ------------------------------------------------------------------ 1. it is running at all
STATE="$(docker inspect --format '{{.State.Status}}' "$CID")"
[[ "$STATE" == "running" ]] && ok "container running" "state=$STATE" || bad "container running" "state=$STATE"

HEALTH="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$CID")"
case "$HEALTH" in
    healthy) ok "container health" "healthy" ;;
    starting) bad "container health" "still starting — re-run in a few seconds" ;;
    none)    bad "container health" "no HEALTHCHECK defined" ;;
    *)       bad "container health" "$HEALTH" ;;
esac

# ------------------------------------------------------------------ 2. the app answers
# Streamlit's health endpoint, probed from inside the container on 127.0.0.1: no host port needed.
APP_PORT="$(docker exec "$CID" python -c '
import os
try:
    from src.config import load_settings
    print(load_settings().port)
except Exception:
    print(os.environ.get("APP_PORT", "2026"))
' 2>/dev/null | tr -d '\r')"
[[ "$APP_PORT" =~ ^[0-9]+$ ]] || APP_PORT=2026

HEALTH_BODY="$(docker exec "$CID" python -c "
import urllib.request
print(urllib.request.urlopen('http://127.0.0.1:$APP_PORT/_stcore/health', timeout=5).read().decode().strip())
" 2>/dev/null | tr -d '\r')"
[[ "$HEALTH_BODY" == "ok" ]] && ok "health endpoint" "127.0.0.1:$APP_PORT/_stcore/health -> $HEALTH_BODY" \
                             || bad "health endpoint" "127.0.0.1:$APP_PORT/_stcore/health -> '${HEALTH_BODY:-no response}'"

ROOT_CODE="$(docker exec "$CID" python -c "
import urllib.request
r = urllib.request.urlopen('http://127.0.0.1:$APP_PORT/', timeout=5)
body = r.read()
print(r.status, 'html' if b'<html' in body.lower() else 'not-html', len(body))
" 2>/dev/null | tr -d '\r')"
[[ "$ROOT_CODE" == 200*html* ]] && ok "root page" "$ROOT_CODE" || bad "root page" "${ROOT_CODE:-no response}"

# ------------------------------------------------------------------ 3. the hardening is real
UID_IN_CONTAINER="$(docker exec "$CID" id -u 2>/dev/null | tr -d '\r')"
if [[ "$UID_IN_CONTAINER" == "0" ]]; then
    bad "runs non-root" "uid 0 — the container is root"
elif [[ "$UID_IN_CONTAINER" =~ ^[0-9]+$ ]]; then
    ok "runs non-root" "uid=$UID_IN_CONTAINER ($(docker exec "$CID" id -un 2>/dev/null | tr -d '\r'))"
else
    bad "runs non-root" "could not read the uid"
fi

READONLY="$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$CID")"
[[ "$READONLY" == "true" ]] && ok "read-only root filesystem" "ReadonlyRootfs=true" \
                            || bad "read-only root filesystem" "ReadonlyRootfs=$READONLY (compose read_only: true)"

PORTS="$(docker port "$CID" 2>/dev/null)"
BINDINGS="$(docker inspect --format '{{json .HostConfig.PortBindings}}' "$CID")"
if [[ -z "$PORTS" && ( "$BINDINGS" == "{}" || "$BINDINGS" == "null" ) ]]; then
    ok "no published host ports" "docker port empty, PortBindings=$BINDINGS"
else
    bad "no published host ports" "docker port: ${PORTS:-none}; PortBindings=$BINDINGS"
fi

CAPS="$(docker inspect --format '{{json .HostConfig.CapDrop}}' "$CID")"
[[ "$CAPS" == *ALL* ]] && ok "capabilities dropped" "CapDrop=$CAPS" || bad "capabilities dropped" "CapDrop=$CAPS"

NONEWPRIV="$(docker inspect --format '{{json .HostConfig.SecurityOpt}}' "$CID")"
[[ "$NONEWPRIV" == *no-new-privileges* ]] && ok "no-new-privileges" "$NONEWPRIV" \
                                          || bad "no-new-privileges" "$NONEWPRIV"

RESTART="$(docker inspect --format '{{.HostConfig.RestartPolicy.Name}}' "$CID")"
case "$RESTART" in
    unless-stopped|always) ok "restart policy" "$RESTART" ;;
    *)                     bad "restart policy" "'$RESTART' — expected unless-stopped" ;;
esac

TMPFS="$(docker inspect --format '{{json .HostConfig.Tmpfs}}' "$CID")"
[[ "$TMPFS" == *"/tmp"* ]] && ok "tmpfs for /tmp" "/tmp is a tmpfs (the rootfs is read-only)" \
                           || bad "tmpfs for /tmp" "no tmpfs on /tmp: $TMPFS"

WRITABLE_MOUNTS="$(docker inspect --format '{{range .Mounts}}{{if .RW}}{{.Destination}} {{end}}{{end}}' "$CID" | tr -d '\r')"
if [[ "$(echo "$WRITABLE_MOUNTS" | wc -w)" -le 1 && "$WRITABLE_MOUNTS" == *"/app/storage"* ]]; then
    ok "single writable mount" "${WRITABLE_MOUNTS% }"
else
    bad "single writable mount" "writable mounts: ${WRITABLE_MOUNTS:-none}"
fi

# ------------------------------------------------------------------ 4. the data and the model
DB_CHECK="$(docker exec "$CID" python -c '
import os, sqlite3
db = os.environ.get("APP_DB_PATH", "/app/storage/aihubcampus.db")
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
print(con.execute("PRAGMA integrity_check").fetchone()[0],
      con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type=\"table\"").fetchone()[0])
con.close()
' 2>/dev/null | tr -d '\r')"
read -r INTEGRITY N_TABLES <<< "$DB_CHECK"
DB_PATH_IN_CONTAINER="$(docker exec "$CID" printenv APP_DB_PATH 2>/dev/null | tr -d '\r')"
if [[ "$INTEGRITY" == "ok" && "${N_TABLES:-0}" -ge 6 ]]; then
    ok "database readable" "integrity_check=ok, $N_TABLES tables at ${DB_PATH_IN_CONTAINER:-/app/storage/aihubcampus.db}"
else
    bad "database readable" "${DB_CHECK:-no response from sqlite}"
fi

# The verifier's exit status is the verdict — its report is prose, and grepping prose is how a
# check quietly stops checking. Only the first line (the model version) is quoted.
ARTIFACT_OUT="$(docker exec "$CID" python -m ml.verify_artifact --models-dir /app/models \
    --csv /app/data/UCI_Credit_Card.csv 2>&1 | tr -d '\r')"
ARTIFACT_RC=$?
if [[ $ARTIFACT_RC -eq 0 ]]; then
    ok "model artifact verifies" "$(echo "$ARTIFACT_OUT" | grep -cE '^\s+\[PASS\]') checks PASS, $(echo "$ARTIFACT_OUT" | grep -E 'artifact_checksum' | sed 's/^ *\[PASS\] //' | cut -c1-58)"
else
    bad "model artifact verifies" "verify_artifact exited $ARTIFACT_RC: $(echo "$ARTIFACT_OUT" | grep -iE 'fail|error' | head -1)"
fi

# ------------------------------------------------------------------ 5. no secret in the tree
if [[ -f scripts/check_no_secrets.py ]]; then
    SECRETS="$(python3 scripts/check_no_secrets.py 2>&1)"
    SCAN_RC=$?
    SCAN_LINE="$(echo "$SECRETS" | tail -1)"
    if [[ $SCAN_RC -eq 0 ]]; then
        ok "secret-pattern scan" "$(echo "$SECRETS" | head -1)"
    else
        bad "secret-pattern scan" "check_no_secrets exited $SCAN_RC: $SCAN_LINE"
    fi
else
    skip "secret-pattern scan" "scripts/check_no_secrets.py is missing"
fi

# ------------------------------------------------------------------ 6. the public surface (optional)
if [[ -n "$PUBLIC_URL" ]]; then
    PUBLIC="$(python3 - "$PUBLIC_URL" <<'PY' 2>&1 | tr -d '\r'
import sys, urllib.error, urllib.request
base = sys.argv[1].rstrip("/")
results = []
# Cloudflare answers 403 to the default `Python-urllib/3.x` User-Agent (browser-integrity /
# bot management), which would make a healthy deployment look broken. A real client sends a
# User-Agent; this one names itself so the request is attributable in the edge logs.
AGENT = "aihubcampus-smoke-test/1.0"
for path in ("/_stcore/health", "/"):
    request = urllib.request.Request(base + path, headers={"User-Agent": AGENT})
    try:
        with urllib.request.urlopen(request, timeout=15) as r:
            body = r.read(2048)
            results.append((path, r.status, len(body), body[:6]))
    except urllib.error.HTTPError as exc:
        results.append((path, exc.code, 0, b""))
    except Exception as exc:                      # noqa: BLE001 - reported, not raised
        results.append((path, "ERR", 0, str(exc).encode()[:80]))
for path, status, size, head in results:
    print(f"{path} {status} {size} {head!r}")
bad = [r for r in results if r[1] != 200]
raise SystemExit(1 if bad else 0)
PY
)"
    if [[ $? -eq 0 ]]; then
        ok "public HTTPS surface" "$PUBLIC_URL ($(echo "$PUBLIC" | wc -l) probe(s) -> 200)"
    else
        bad "public HTTPS surface" "$PUBLIC_URL -> $(echo "$PUBLIC" | tr '\n' ' ')"
    fi
else
    skip "public HTTPS surface" "no --url given (S13 owns the tunnel check)"
fi

# ------------------------------------------------------------------ summary
printf '\n%s\n' "----------------------------------------------------------------"
printf 'RESULT: %d passed, %d failed, %d skipped\n' "$PASS" "$FAIL" "$SKIP"
if [[ $FAIL -gt 0 ]]; then
    printf 'failed checks: %s\n' "${FAILED_NAMES[*]}"
    exit 1
fi
printf 'SMOKE TEST PASSED — the running stack is the hardened stack and it serves.\n'
exit 0
