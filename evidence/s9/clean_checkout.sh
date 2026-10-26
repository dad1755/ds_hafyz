#!/usr/bin/env bash
# A clean checkout of the committed tree, with no working-directory state, runs the whole suite.
set -uo pipefail
REPO="/home/ec-user/non_prod/hafyz_ds"
TMP="$(mktemp -d /tmp/s9-clean-XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

echo "\$ git clone --branch s9/dataset-manager $REPO $TMP/repo"
git clone --quiet --branch s9/dataset-manager "$REPO" "$TMP/repo"
echo "cloned at: $(git -C "$TMP/repo" rev-parse --short HEAD) $(git -C "$TMP/repo" log -1 --pretty=%s)"
echo "tracked files: $(git -C "$TMP/repo" ls-files | wc -l)"
echo "untracked/modified after clone: $(git -C "$TMP/repo" status --porcelain | wc -l)"
echo "seed present: $(test -f "$TMP/repo/data/UCI_Credit_Card.csv" && echo yes || echo no)"
echo "artifact present: $(test -f "$TMP/repo/models/best_pipeline.joblib" && echo yes || echo no)"
echo "no .env in the clone: $(test ! -e "$TMP/repo/.env" && echo confirmed || echo PRESENT)"
echo
echo "\$ docker run --rm -v <clean clone>:/app:z -w /app aihubcampus-web:s9 python -m pytest tests -q -p no:cacheprovider"
docker run --rm -v "$TMP/repo:/app:z" -w /app aihubcampus-web:s9 python -m pytest tests -q -p no:cacheprovider
echo "exit=$?"
