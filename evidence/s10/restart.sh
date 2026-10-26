#!/usr/bin/env bash
# Recreate the deployed web service on the freshly built image and render the S10 page inside
# the restarted container.
#
#   bash evidence/s10/restart.sh > evidence/s10/restart.txt 2>&1
#
# The point of this file is the restart: the figures have to come back after the process that
# drew them is gone. Everything printed below is read from the running container.
set -uo pipefail
cd "$(dirname "$0")/../.."

echo "\$ docker compose config --quiet"
docker compose config --quiet && echo "compose valid"
echo

echo "\$ docker inspect aihubcampus-web-1 --format '{{.Id}} started={{.State.StartedAt}} image={{.Image}}'"
docker inspect aihubcampus-web-1 --format '{{.Id}} started={{.State.StartedAt}} image={{.Image}}'
echo

echo "\$ docker compose up -d --no-deps web"
docker compose up -d --no-deps web
echo

echo "\$ # wait for the healthcheck"
for _ in $(seq 1 60); do
  status="$(docker inspect aihubcampus-web-1 --format '{{.State.Health.Status}}' 2>/dev/null || echo unknown)"
  [ "$status" = "healthy" ] && break
  sleep 2
done
docker inspect aihubcampus-web-1 \
  --format 'after restart: id={{.Id}} started={{.State.StartedAt}} health={{.State.Health.Status}} image={{.Image}}'
echo

echo "\$ docker compose ps"
docker compose ps
echo

echo "\$ docker exec aihubcampus-web-1 python -c '<health endpoint>'"
docker exec aihubcampus-web-1 python -c \
  "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:2026/_stcore/health', timeout=3).read().decode())"
echo

echo "\$ docker port aihubcampus-web-1   # no published host port is expected"
docker port aihubcampus-web-1 || true
echo

echo "\$ docker exec aihubcampus-web-1 ls -l /app/models /app/models/eda /app/models/figures"
docker exec aihubcampus-web-1 ls -l /app/models /app/models/eda /app/models/figures
echo

# The probe is copied in as a file rather than piped on stdin: Streamlit's AppTest reads the
# script's source with `inspect`, which cannot resolve a module that arrived on stdin.
echo "\$ docker cp evidence/s10/probe_evaluation.py aihubcampus-web-1:/tmp/s10_probe.py"
docker cp evidence/s10/probe_evaluation.py aihubcampus-web-1:/tmp/s10_probe.py
echo "\$ docker exec -e PYTHONPATH=/app aihubcampus-web-1 python /tmp/s10_probe.py"
docker exec -e PYTHONPATH=/app aihubcampus-web-1 python /tmp/s10_probe.py
probe_status=$?
docker exec aihubcampus-web-1 rm -f /tmp/s10_probe.py >/dev/null 2>&1 || true
echo "probe exit=$probe_status"
echo

if [ "$probe_status" -eq 0 ]; then
  echo "RESULT: PASS — the restarted container renders all 11 figures from its own artifacts"
  exit 0
fi
echo "RESULT: FAIL — the restarted container did not render the evaluation page"
exit 1
