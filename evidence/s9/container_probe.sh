#!/usr/bin/env bash
# S9 runtime probe: what the running container knows about datasets, and can it quarantine?
# Read-only except for one throwaway file inside the quarantine directory, removed at the end.
set -uo pipefail
cd /home/ec-user/non_prod/hafyz_ds

echo "\$ docker ps --filter label=com.docker.compose.project=aihubcampus"
docker ps --filter label=com.docker.compose.project=aihubcampus --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
echo
echo "\$ docker inspect aihubcampus-web-1 --format 'health={{.State.Health.Status}} image={{.Image}}'"
docker inspect aihubcampus-web-1 --format 'health={{.State.Health.Status}} image={{.Image}}'
echo
echo "\$ docker exec aihubcampus-web-1 ls /app/src"
docker exec aihubcampus-web-1 ls /app/src
echo
echo "\$ sha256sum src/data_manager.py src/pages_datasets.py   # the tree on the host"
sha256sum src/data_manager.py src/pages_datasets.py
echo
echo "\$ docker exec aihubcampus-web-1 sha256sum /app/src/data_manager.py /app/src/pages_datasets.py"
docker exec aihubcampus-web-1 sha256sum /app/src/data_manager.py /app/src/pages_datasets.py
echo
echo "\$ docker exec aihubcampus-web-1 python -c '<print dataset_versions>'"
docker exec -i aihubcampus-web-1 python - <<'PY'
import sqlite3
conn = sqlite3.connect('/app/storage/aihubcampus.db')
conn.row_factory = sqlite3.Row
print("dataset_versions:")
for row in conn.execute(
    "SELECT id, original_filename_safe, sha256, record_count, column_count, class_zero, "
    "class_one, is_active, status, quarantined_filename FROM dataset_versions ORDER BY id"
):
    print(dict(row))
print("active_rows =", conn.execute(
    "SELECT COUNT(*) FROM dataset_versions WHERE is_active = 1").fetchone()[0])
print("dataset_rejections rows =", conn.execute(
    "SELECT COUNT(*) FROM dataset_rejections").fetchone()[0])
print("migrations:", [r[0] for r in conn.execute(
    "SELECT version FROM schema_migrations ORDER BY version")])
PY
echo
echo "\$ docker exec aihubcampus-web-1 python -c '<model manifest dataset sha>'"
docker exec -i aihubcampus-web-1 python - <<'PY'
import json
manifest = json.load(open('/app/models/model_manifest.json'))
print("manifest dataset sha256 =", manifest['dataset']['sha256'])
print("manifest artifact sha256 =", manifest['artifact']['sha256'])
print("manifest model version  =", manifest['model']['version'])
PY
echo
echo "\$ docker exec aihubcampus-web-1 python -c '<quarantine writable>'"
docker exec -i aihubcampus-web-1 python - <<'PY'
from pathlib import Path
directory = Path('/app/storage/quarantine')
directory.mkdir(parents=True, exist_ok=True)
probe = directory / 's9-probe.csv'
probe.write_text('probe\n')
print("wrote and read back:", probe.read_text().strip(), "at", probe)
probe.unlink()
print("removed:", not probe.exists())
print("seed read-only mount present:", Path('/app/data/UCI_Credit_Card.csv').is_file())
PY
echo
echo "\$ docker exec aihubcampus-web-1 python -c '<health endpoint>'"
docker exec aihubcampus-web-1 python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:2026/_stcore/health', timeout=3).read().decode())"
echo
echo "\$ docker compose config   # published host ports (expect none)"
docker compose config | grep -n "published\|host_ip" || echo "no published host ports"
