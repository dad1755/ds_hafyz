#!/usr/bin/env bash
# S16 independent gate re-run — the QA agent's own transcript (agent 7899db8c).
# Read-only: no deploy, no restart, no recreate, no migration, no push.
# Run from the release checkout:  bash evidence/s16/qa_gate_rerun.sh
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 2
S="${QA_SCRATCH:?QA_SCRATCH must point at the scratch dir holding the smoke output}"
say() { printf '\n=== %s ===\n' "$1"; }

printf '# S16 independent gate re-run — transcript\n'
printf '# run (UTC):   %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '# host:        %s · %s\n' "$(hostname)" "$(uname -r)"
printf '# tag:         v1.0.0 -> %s\n' "$(git rev-parse 'v1.0.0^{commit}')"
printf '# branch:      %s (unmerged, unpushed)\n' "$(git branch --show-current)"
printf '# verifier:    7899db8c-d8b0-42cd-b300-dd5d0f0ae46e (independent of the implementer a83f3cb1)\n'

say "1. host and daemon state at the start of the run"
printf '$ uptime\n'; uptime
printf '$ systemctl is-active docker\n'; systemctl is-active docker
printf '$ cat /proc/pressure/io\n'; cat /proc/pressure/io
printf '$ docker info --format "{{.Containers}} total / {{.ContainersRunning}} running"\n'
docker info --format '{{.Containers}} total / {{.ContainersRunning}} running'

say "2. the release tag, and what the running image actually contains"
printf '$ git describe --tags --exact-match\n'; git describe --tags --exact-match
printf '$ git status --porcelain\n'; git status --porcelain
printf '$ git diff --stat 49540a6 v1.0.0 | tail -3\n'; git diff --stat 49540a6 v1.0.0 | tail -3
printf '$ git diff --name-only 49540a6 v1.0.0 | grep -E "\\.py$" | grep -v "^evidence/" | wc -l\n'
git diff --name-only 49540a6 v1.0.0 | grep -E '\.py$' | grep -v '^evidence/' | wc -l
printf '  (0 = no application code changed between the S13 test run and this tag)\n'
printf '$ compare every tagged .py against the file inside the serving image\n'
TAG_PY=$(mktemp -d); git archive v1.0.0 | tar -x -C "$TAG_PY"
IMG=$(mktemp)
docker exec aihubcampus-web-1 sh -c 'cd /app && find . -name "*.py" -not -path "./tests/*" | sed "s|^\./||" | sort | xargs sha256sum' > "$IMG"
python3 - "$TAG_PY" "$IMG" <<'PY'
import hashlib, pathlib, sys
tag, img_file = pathlib.Path(sys.argv[1]), sys.argv[2]
img = {}
for line in open(img_file):
    p = line.split()
    if len(p) == 2:
        img[p[1]] = p[0]
same = diff = 0
for f in tag.rglob('*.py'):
    rel = str(f.relative_to(tag))
    if rel.startswith(('tests/', 'evidence/')) or '__pycache__' in rel:
        continue
    if rel in img and img[rel] == hashlib.sha256(f.read_bytes()).hexdigest():
        same += 1
    else:
        diff += 1
print(f'  {same} identical, {diff} differing')
PY
rm -rf "$TAG_PY" "$IMG"

say "3. gates A and B — data and model, re-derived from the tag"
printf '$ sha256sum data/UCI_Credit_Card.csv (from the tag)\n'
git show 'v1.0.0:data/UCI_Credit_Card.csv' | sha256sum
printf '$ python3 - (held-out block of models/metrics.json)\n'
python3 - <<'PY'
import json
m = json.load(open('models/metrics.json'))
e = m['evaluation']
d = e['models']['decision_tree']
print('  test rows:', e['test_rows'], '| threshold:', e['threshold'], '| scored:', e['scored_once'])
print('  decision_tree metrics:', json.dumps(d['metrics'], sort_keys=True))
print('  confusion matrix    :', json.dumps(d['confusion_matrix'], sort_keys=True))
print('  arithmetic check    :', d['arithmetic_check']['verdict'], '| max_abs_delta', d['arithmetic_check']['max_abs_delta'])
print('  baseline (constant) :', json.dumps(e['baseline']['metrics'], sort_keys=True))
print('  selection           :', m['selection']['decided_by'])
PY

say "4. gate D — the container checks, on the serving container (docker exec, not docker run)"
printf '$ docker exec aihubcampus-web-1 sh -c "test ! -e /app/.env && echo ENV_ABSENT"\n'
docker exec aihubcampus-web-1 sh -c 'test ! -e /app/.env && echo "  ENV_ABSENT"'
printf '$ docker exec aihubcampus-web-1 sh -c "test -f /app/models/best_pipeline.joblib && test ! -w ... && echo MODEL_NOT_WRITABLE"\n'
docker exec aihubcampus-web-1 sh -c 'test -f /app/models/best_pipeline.joblib && test ! -w /app/models/best_pipeline.joblib && echo "  MODEL_NOT_WRITABLE"'
printf '$ docker exec aihubcampus-web-1 id\n'
docker exec aihubcampus-web-1 id | sed 's/^/  /'
printf '$ docker image inspect aihubcampus-web:local --format "{{range .Config.Env}}{{println .}}{{end}}" | grep -cE "^(INITIAL_ADMIN_PASSWORD|INITIAL_USER_PASSWORD|APP_SESSION_SECRET|TUNNEL_TOKEN)="\n'
printf '  credential-shaped variables in the image: '
docker image inspect aihubcampus-web:local --format '{{range .Config.Env}}{{println .}}{{end}}' | grep -cE '^(INITIAL_ADMIN_PASSWORD|INITIAL_USER_PASSWORD|APP_SESSION_SECRET|TUNNEL_TOKEN)=' || true
printf '$ docker port aihubcampus-web-1   (empty = nothing published on the host)\n'
docker port aihubcampus-web-1 | sed 's/^/  /'
printf '$ docker inspect aihubcampus-web-1 --format user/readonly/restart\n'
docker inspect aihubcampus-web-1 --format '  user={{.Config.User}} readonly_rootfs={{.HostConfig.ReadonlyRootfs}} restart={{.HostConfig.RestartPolicy.Name}}'

say "5. the model artifact inside the image, against the manifest"
printf '$ docker exec ... python - (artifact sha256, feature order, parity with the CLI)\n'
docker exec -i aihubcampus-web-1 python - < "$(dirname "$0")/qa_parity.py" 2>&1 | sed 's/^/  /'

say "6. the release gate script at the tag — how far it got before the daemon stalled"
printf '$ TAG=v1.0.0 bash evidence/s16/release_gate.sh --with-tests\n'
printf '  (full output: the release_gate section of this file, from the run at 23:19:27Z)\n'
cat "$S/s16_gate_rerun.txt" | sed 's/^/  /'
printf '\n$ docker run --rm --network none aihubcampus-web:local test -r /app/models/best_pipeline.joblib   (control probe)\n'
timeout 60 docker run --rm --network none aihubcampus-web:local test -r /app/models/best_pipeline.joblib
printf '  exit=%s  (124 = still cannot start a container: the host-wide stall, not a release defect)\n' "$?"
printf '$ docker ps -a --format "{{.Names}} {{.Status}}" | grep Created | wc -l\n'
docker ps -a --format '{{.Names}} {{.Status}}' | grep -c ' Created' || true
printf '  (containers other agents created and the daemon never started — the stall is host-wide)\n'

say "7. gate E — the backup bundle, and the live data after the reboot"
printf '$ sha256sum -c aihubcampus-20261027T162831Z.tar.gz.sha256\n'
( cd /home/ec-user/non_prod/aihubcampus_release_backups/s16 && sha256sum -c aihubcampus-20261027T162831Z.tar.gz.sha256 | sed 's/^/  /' )
printf '$ tar -tzf ... (what a restore gets)\n'
tar -tzf /home/ec-user/non_prod/aihubcampus_release_backups/s16/aihubcampus-20261027T162831Z.tar.gz | sed 's/^/  /'
printf '$ the host rebooted at 22:56Z; the volume came back with the container\n'
docker exec aihubcampus-web-1 python -c "
import sqlite3, hashlib, os
p = os.environ.get('APP_DB_PATH', '/app/storage/aihubcampus.db')
print('  db sha256   :', hashlib.sha256(open(p, 'rb').read()).hexdigest())
c = sqlite3.connect('file:' + p + '?mode=ro', uri=True)
print('  integrity   :', c.execute('pragma integrity_check').fetchone()[0])
for t in ('audit_events', 'dataset_rejections', 'dataset_versions', 'login_attempts', 'prediction_logs', 'schema_migrations', 'sessions', 'users'):
    print('  %-18s %s' % (t, c.execute('select count(*) from ' + t).fetchone()[0]))
" 2>&1 | sed 's/^/  /'

say "8. gate E — the public URL, and both roles through a real browser"
printf '$ curl -sS -o /dev/null -w "%%{http_code} %%{time_total}s" https://www.aihubcampus.online/\n'
curl -sS -o /dev/null -w '  %{http_code} %{time_total}s\n' https://www.aihubcampus.online/
printf '$ curl -sS https://www.aihubcampus.online/_stcore/health\n'
curl -sS https://www.aihubcampus.online/_stcore/health | sed 's/^/  /'; echo
printf '$ node evidence/s16/qa_s16_smoke.js   (this verifier'"'"'s own smoke, not the implementer'"'"'s)\n'
sed 's/^/  /' "$S/qa_s16_smoke_out.txt"

say "9. the secret scan, on the tag tree"
printf '$ python3 scripts/check_no_secrets.py --all-files   (in a clean clone of the tag)\n'
CLONE=$(mktemp -d); git clone --quiet --branch v1.0.0 . "$CLONE/release" 2>/dev/null
( cd "$CLONE/release" && python3 scripts/check_no_secrets.py --all-files | sed 's/^/  /' )
rm -rf "$CLONE"

printf '\n# end of transcript — %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
