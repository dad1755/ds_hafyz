#!/usr/bin/env bash
# Recreate the aihubcampus web service on the freshly built image.
set -euo pipefail
cd /home/ec-user/non_prod/hafyz_ds
docker compose config --quiet
echo "compose valid"
docker compose up -d --no-deps web
sleep 30
docker ps --filter label=com.docker.compose.project=aihubcampus --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
docker inspect aihubcampus-web-1 --format 'health={{.State.Health.Status}} started={{.State.StartedAt}} image={{.Image}}'
