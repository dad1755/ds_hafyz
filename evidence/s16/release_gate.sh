#!/usr/bin/env bash
# S16 release gate — `scripts/verify_release.sh` run against the RELEASE TAG, in a clone.
#
#   TAG=v1.0.0 bash evidence/s16/release_gate.sh > evidence/s16/release_gate.txt 2>&1
#
# Why a clone and not the working checkout: the working checkout is a shared, in-place tree that
# also carries an untracked blueprint belonging to a different project on this host. The release
# tree is what the tag contains, so the gate runs on exactly that — `git clone --branch <tag>` —
# plus the two git-ignored files the operator owns (.env and the seed CSV). Nothing else is
# copied, which is also the reproducibility statement: the tag plus two operator inputs is the
# whole deployment.
#
# The clone is deleted afterwards. The live stack is not rebuilt, restarted or reconfigured here:
# the gate's smoke section reads the running containers, and `--build` is deliberately omitted so
# this run cannot retag the image that is currently serving.
#
# Usage: TAG=v1.0.0 bash evidence/s16/release_gate.sh [--with-tests]
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2

REPO_ROOT="$PWD"
TAG="${TAG:?TAG must name the release tag}"
EXTRA=("$@")
WORK="$(mktemp -d "${TMPDIR:-/tmp}/s16-gate.XXXXXXXX")"
CLONE="$WORK/release"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

echo "# S16 release gate — scripts/verify_release.sh on the release tag, in a clean clone"
echo "# run (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "# host:      $(hostname) · $(uname -r)"
echo "# tag:       $TAG -> $(git rev-parse "$TAG^{commit}")"
echo "# clone:     $CLONE (deleted at the end of this run)"
echo

echo "=== the release tree, as the tag defines it ==="
echo "\$ git clone --quiet --branch $TAG $REPO_ROOT $CLONE"
git clone --quiet --branch "$TAG" "$REPO_ROOT" "$CLONE" || { echo "clone FAILED"; exit 1; }
git -C "$CLONE" log --oneline -1
echo "\$ git -C clone describe --tags --exact-match"
git -C "$CLONE" describe --tags --exact-match
echo
echo "\$ cp .env data/UCI_Credit_Card.csv   (the two operator-supplied, git-ignored inputs)"
cp "$REPO_ROOT/.env" "$CLONE/.env"
cp "$REPO_ROOT/data/UCI_Credit_Card.csv" "$CLONE/data/UCI_Credit_Card.csv"
echo "  .env                     : $(stat -c%s "$CLONE/.env") bytes (not printed, not hashed)"
echo "  data/UCI_Credit_Card.csv : $(stat -c%s "$CLONE/data/UCI_Credit_Card.csv") bytes, sha256 $(sha256sum "$CLONE/data/UCI_Credit_Card.csv" | cut -d' ' -f1)"
echo
echo "\$ git -C clone status --porcelain   (the only untracked entries are those two inputs)"
git -C "$CLONE" status --porcelain | sed 's/^/  /'
echo
echo "# for contrast, the working checkout this run was launched from:"
echo "\$ git -C $REPO_ROOT status --porcelain"
git -C "$REPO_ROOT" status --porcelain | sed 's/^/  /'
echo "  (DATASCIENCE_UI_POLISH_BLUEPRINT.md is another project's untracked file in this shared"
echo "   checkout; it is not in the tag and therefore not in the release tree above)"
echo

echo "=== scripts/verify_release.sh ${EXTRA[*]:-} ==="
( cd "$CLONE" && bash scripts/verify_release.sh "${EXTRA[@]}" )
RC=$?
echo
echo "verify_release.sh exit=$RC"
exit "$RC"
