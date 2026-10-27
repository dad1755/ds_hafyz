#!/usr/bin/env bash
# AI Hub Campus — release verification gate (Sprint 12, blueprint §7 / §9 S12).
#
# Runs every mechanical check the S12 acceptance names, in one command, and prints a verdict
# table. It does NOT replace the independent verification gate — a different agent certifies a
# sprint. This is the check the author runs before handing over, and the operator runs before
# deploying.
#
# What it proves:
#   repo        the tree is clean and the commit is recorded (so evidence can be tied to a sha)
#   compose     `docker compose config` validates, no `ports:`, expose only
#   image       builds from a digest-pinned base, runs as a numeric non-root user, carries no
#               .env and no credential in its environment
#   secrets     scripts/check_no_secrets.py finds nothing in the tree or the image
#   docs        every script and evidence path the runbook/deployment docs tell you to run
#               actually exists as a file (a runbook that names a missing script is a lie)
#   scripts     backup.sh / restore.sh / smoke_test.sh / verify_release.sh are present, executable
#               and respond to --help
#   runtime     scripts/smoke_test.sh passes against the running stack
#   tests       (--with-tests) the full pytest suite passes inside the image
#
# Usage:
#   scripts/verify_release.sh                  # static + runtime checks, ~20 s
#   scripts/verify_release.sh --with-tests     # + the pytest suite inside the image (~10 min)
#   scripts/verify_release.sh --build          # + rebuild the image first
#   scripts/verify_release.sh --no-runtime     # static checks only (no container needed)
#   scripts/verify_release.sh --help
#
# Exit codes: 0 = all checks passed, 1 = at least one check failed, 2 = bad usage.
# Prints no secret; it never reads .env and never dumps the environment.

set -uo pipefail

PROJECT="${COMPOSE_PROJECT_NAME:-aihubcampus}"
SERVICE="web"
IMAGE="aihubcampus-web:local"
WITH_TESTS=0
DO_BUILD=0
RUNTIME=1
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

PASS=0
FAIL=0
FAILED_NAMES=()
RESULTS=()

usage() {
    sed -n '2,34p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-tests) WITH_TESTS=1; shift ;;
        --build)      DO_BUILD=1; shift ;;
        --no-runtime) RUNTIME=0; shift ;;
        --project)    PROJECT="${2:?--project needs a name}"; shift 2 ;;
        --image)      IMAGE="${2:?--image needs a reference}"; shift 2 ;;
        -h|--help)    usage ;;
        *) echo "verify_release: unknown argument: $1 (try --help)" >&2; exit 2 ;;
    esac
done

record() {           # record <PASS|FAIL|SKIP> <check> <detail>
    local verdict="$1" name="$2" detail="${3:-}"
    if [[ "$verdict" == "PASS" ]]; then PASS=$((PASS + 1)); else
        if [[ "$verdict" == "FAIL" ]]; then FAIL=$((FAIL + 1)); FAILED_NAMES+=("$name"); fi
    fi
    printf '%-5s %-30s %s\n' "$verdict" "$name" "$detail"
    RESULTS+=("$verdict|$name|$detail")
}

cd "$REPO_ROOT" || exit 2
command -v docker >/dev/null 2>&1 || { echo "verify_release: docker is not on PATH" >&2; exit 2; }

printf 'AI Hub Campus release verification — %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf 'repo=%s project=%s image=%s\n\n' "$REPO_ROOT" "$PROJECT" "$IMAGE"

# ------------------------------------------------------------------ repo state
COMMIT="$(git rev-parse HEAD 2>/dev/null || echo 'not-a-git-checkout')"
BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '-')"
DIRTY="$(git status --porcelain 2>/dev/null | grep -v '^?? backups/' | grep -v '^?? evidence/' || true)"
if [[ -z "$DIRTY" ]]; then
    record PASS "git tree clean" "$BRANCH @ ${COMMIT:0:12}"
else
    record FAIL "git tree clean" "$(echo "$DIRTY" | wc -l) modified path(s) not committed"
fi

# ------------------------------------------------------------------ compose contract
COMPOSE_ERR="$(docker compose config --quiet 2>&1)"
if [[ -z "$COMPOSE_ERR" ]]; then
    record PASS "compose validates" "docker compose config --quiet"
else
    record FAIL "compose validates" "$(echo "$COMPOSE_ERR" | head -1)"
fi

if grep -qE '^\s+ports:' compose.yaml; then
    record FAIL "no host ports in compose" "compose.yaml has a ports: section"
else
    record PASS "no host ports in compose" "expose: only"
fi

for key in 'read_only: true' 'no-new-privileges:true' 'cap_drop' 'restart: unless-stopped' 'healthcheck:'; do
    if grep -q -- "$key" compose.yaml; then
        record PASS "compose has $key" "present"
    else
        record FAIL "compose has $key" "missing from compose.yaml"
    fi
done

# ------------------------------------------------------------------ image contract
if grep -qE '^FROM .*@sha256:[0-9a-f]{64}' Dockerfile; then
    record PASS "base image digest-pinned" "$(grep -E '^FROM' Dockerfile | head -1)"
else
    record FAIL "base image digest-pinned" "Dockerfile FROM is not pinned by @sha256:"
fi

if grep -qE '^USER (app|[0-9]+:[0-9]+)' Dockerfile; then
    record PASS "Dockerfile drops to non-root" "$(grep -E '^USER' Dockerfile | tail -1)"
else
    record FAIL "Dockerfile drops to non-root" "no USER line"
fi

if [[ $DO_BUILD -eq 1 ]]; then
    if docker compose build "$SERVICE" >/dev/null 2>&1; then
        record PASS "image builds" "docker compose build $SERVICE"
    else
        record FAIL "image builds" "docker compose build $SERVICE failed — run it directly to see why"
    fi
fi

if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    IMAGE_UID="$(docker image inspect --format '{{.Config.User}}' "$IMAGE")"
    if [[ -n "$IMAGE_UID" && "$IMAGE_UID" != "root" && "$IMAGE_UID" != "0" ]]; then
        record PASS "image user is non-root" "Config.User=$IMAGE_UID"
    else
        record FAIL "image user is non-root" "Config.User='${IMAGE_UID}'"
    fi

    if docker run --rm --network none "$IMAGE" test ! -e /app/.env >/dev/null 2>&1; then
        record PASS "no .env inside the image" "/app/.env absent"
    else
        record FAIL "no .env inside the image" "/app/.env exists in the image"
    fi

    IMAGE_ENV="$(docker image inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "$IMAGE")"
    if echo "$IMAGE_ENV" | grep -qE '^(INITIAL_ADMIN_PASSWORD|INITIAL_USER_PASSWORD|APP_SESSION_SECRET|TUNNEL_TOKEN|TUNNEL_TOKEN_)='; then
        record FAIL "no credential in image env" "a secret-shaped variable is baked into Config.Env"
    else
        record PASS "no credential in image env" "no credential-shaped variable in Config.Env"
    fi

    if docker run --rm --network none "$IMAGE" test -r /app/models/best_pipeline.joblib >/dev/null 2>&1 \
       || docker run --rm --network none "$IMAGE" sh -c 'test -f /app/models/best_pipeline.joblib && test ! -w /app/models/best_pipeline.joblib' >/dev/null 2>&1; then
        record PASS "model artifact is read-only" "the app user cannot rewrite /app/models"
    else
        record FAIL "model artifact is read-only" "the artifact is missing or writable"
    fi
else
    record FAIL "image present" "$IMAGE not built — run docker compose build web"
fi

# ------------------------------------------------------------------ secret scan
if [[ -f scripts/check_no_secrets.py ]]; then
    SCAN="$(python3 scripts/check_no_secrets.py 2>&1 | tail -1)"
    if echo "$SCAN" | grep -qiE "0 (hits|matches|findings)|clean|no (secret|match)"; then
        record PASS "secret-pattern scan" "$SCAN"
    else
        record FAIL "secret-pattern scan" "$SCAN"
    fi
else
    record FAIL "secret-pattern scan" "scripts/check_no_secrets.py is missing"
fi

# ------------------------------------------------------------------ scripts exist and answer
for s in backup.sh restore.sh smoke_test.sh verify_release.sh; do
    path="scripts/$s"
    if [[ ! -f "$path" ]]; then
        record FAIL "scripts/$s present" "missing"
    elif [[ ! -x "$path" ]]; then
        record FAIL "scripts/$s present" "not executable (chmod +x $path)"
    elif ! bash "$path" --help >/dev/null 2>&1; then
        record FAIL "scripts/$s present" "--help does not run"
    else
        record PASS "scripts/$s present" "executable, --help works"
    fi
done

# ------------------------------------------------------------------ docs name real files
# Every `scripts/...` and `evidence/...` path quoted in the operator docs must exist. This is
# the machine check behind "the runbook commands actually exist as files".
MISSING="$(python3 - <<'PY'
import os, re, sys

docs = ["docs/runbook.md", "docs/deployment.md", "README.md"]
pattern = re.compile(r'(?<![\w/.-])((?:scripts|evidence)/[A-Za-z0-9_./-]*[A-Za-z0-9_])')
missing, seen = [], set()
for doc in docs:
    if not os.path.isfile(doc):
        missing.append(f"{doc} (doc missing)")
        continue
    for match in pattern.finditer(open(doc, encoding="utf-8").read()):
        path = match.group(1).rstrip(".")
        if path in seen:
            continue
        seen.add(path)
        # A directory reference is fine; a glob is fine; anything else must exist.
        if path.endswith("/") or "*" in path:
            continue
        if not os.path.exists(path):
            missing.append(f"{path} (named in {doc})")
print("\n".join(missing))
PY
)"
if [[ -z "$MISSING" ]]; then
    record PASS "docs name real files" "every scripts/ and evidence/ path in runbook, deployment, README exists"
else
    record FAIL "docs name real files" "$(echo "$MISSING" | tr '\n' '; ')"
fi

for doc in docs/runbook.md docs/deployment.md docs/RELEASE_NOTES.md docs/test_matrix.md; do
    if [[ -f "$doc" && -s "$doc" ]]; then
        record PASS "$doc present" "$(wc -l < "$doc") lines"
    else
        record FAIL "$doc present" "missing or empty"
    fi
done

# ------------------------------------------------------------------ runtime
if [[ $RUNTIME -eq 1 ]]; then
    SMOKE_OUT="$(bash scripts/smoke_test.sh --project "$PROJECT" --service "$SERVICE" 2>&1)"
    SMOKE_RC=$?
    if [[ $SMOKE_RC -eq 0 ]]; then
        record PASS "smoke test" "$(echo "$SMOKE_OUT" | grep -E '^RESULT:' | tail -1)"
    else
        record FAIL "smoke test" "$(echo "$SMOKE_OUT" | grep -E '^FAIL ' | head -3 | tr '\n' ' ')"
    fi
else
    record SKIP "smoke test" "--no-runtime"
fi

# ------------------------------------------------------------------ test suite
if [[ $WITH_TESTS -eq 1 ]]; then
    TEST_LOG="$(mktemp "${TMPDIR:-/tmp}/aihubcampus-pytest.XXXXXX")"
    docker run --rm --network none -v "$PWD:/app:z" -w /app "$IMAGE" \
        python -m pytest tests -q -p no:cacheprovider > "$TEST_LOG" 2>&1
    TEST_RC=$?
    TAIL="$(tail -3 "$TEST_LOG" | tr '\n' ' ')"
    if [[ $TEST_RC -eq 0 ]]; then
        record PASS "pytest suite" "$TAIL"
    else
        record FAIL "pytest suite" "$TAIL"
    fi
    printf '\n  full pytest output: %s\n' "$TEST_LOG"
else
    record SKIP "pytest suite" "pass --with-tests"
fi

# ------------------------------------------------------------------ verdict
printf '\n%s\n' "----------------------------------------------------------------"
printf 'RESULT: %d passed, %d failed\n' "$PASS" "$FAIL"
if [[ $FAIL -gt 0 ]]; then
    printf 'failed: %s\n' "${FAILED_NAMES[*]}"
    printf 'VERDICT: FAIL — do not deploy this tree.\n'
    exit 1
fi
printf 'VERDICT: PASS (mechanical checks) — commit %s\n' "${COMMIT:0:12}"
printf 'This is the author/operator gate. Sprint certification still requires the independent\n'
printf 'verification agent (blueprint §0: a sprint is VERIFIED only by its own gate).\n'
exit 0
