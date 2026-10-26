# S11 evidence — automated testing and adversarial verification

Everything here is real command output captured on ridergami2 on 2026-10-27 against the
committed tree. Each `.sh`/`.py` probe prints the command it ran before its output and exits
non-zero when a check fails, so none of it can pass by printing a sentence. The mapping from
each requirement to the test id that exercises it lives in `docs/test_matrix.md`.

| File | What it shows |
|---|---|
| `test-results/pytest_all_verbose.txt` | The whole suite in the built image, verbatim: **285 passed in 598.66s (0:09:58)**, 0 failed, 0 error, 0 skipped, one `PASSED` line per test (params included) with its timing. This is the raw record every quote in `docs/test_matrix.md` comes from. |
| `test-results/t_matrix_extract.txt` | `extract_matrix.py`'s output: T01–T12 each resolved to its cited node ids and their verdicts, read out of the transcript above. `RESULT: PASS — every cited test id appears in the raw run as PASSED (12 requirements, 285 executed test cases)`. A citation that vanished or failed would make it exit 1. |
| `test-results/compileall.txt` | `python -m compileall -q app.py src ml` → `compileall exit=0`, 39 `.pyc` files, no `Error compiling`. Compiled from a writable copy inside the container because the bind-mounted tree belongs to the operator and the container runs as `app`; the first attempt wrote into the mount and failed with `PermissionError`, not a syntax error. |
| `test-results/check_no_secrets.txt` | `scripts/check_no_secrets.py`: `scanned 255 file(s); 4 secret value(s) loaded from operator env … PASS` for tracked files, and `scanned 264 file(s) … PASS` with `--all-files`. The four values are used as search needles and never printed. |
| `test-results/demo_prediction.txt` | The synthetic demonstrator row scored directly by the shipped artifact — `class 1`, `probability 0.7195348837209302`, band `High`, version `aihubcampus-default-risk-1+48ce02563b2a`, and the band's advice sentence. These are the numbers T07 requires the page to print, produced without the page. |
| `probe_http.txt` | Live checks through the Cloudflare tunnel against `https://www.aihubcampus.online` (and the apex): health `200 body=ok`; sign-in shell `text/html`; `_streamlit_xsrf` issued `SameSite=Lax; Path=/`; **six** candidate file paths (`/storage/aihubcampus.db`, `/app/storage/aihubcampus.db`, `…-wal`, `/data/UCI_Credit_Card.csv`, `/models/best_pipeline.joblib`, `/.env`) all return the SPA HTML shell and none carries the `SQLite format 3\0` header — the body is inspected because Streamlit answers `200` for every unknown path; `Access-Control-Allow-Origin` absent for `https://evil.example`, `null`, `http://127.0.0.1:2026`; WebSocket `101` from the real origin, `403` from a foreign one. `RESULT: PASS`. |
| `probe_logs.txt` | The running container's log scanned against the four real operator secrets (needles only, never printed) plus a password-assignment regex, an `$argon2…` hash pattern, a key-block pattern and a tunnel-token shape: 9 lines / 611 bytes, `PASS — no operator secret, no password assignment, no hash and no key block in the log`. |
| `restart.txt` | **T11 at deployment level.** `ml.verify_artifact` passes its 11 checks before the restart; row counts read from the live database; the demo user signs in inside the container (token held in a mode-600 host file, fed back on stdin, never on a command line); `docker compose up -d --force-recreate web` recreates the container (`started=2026-10-26T23:19:25Z`, `healthy` after 8 polls); after the restart the row counts are still there (`users 2, sessions 4→5, dataset_versions 1, audit_events 14→16`), the **pre-restart token still resolves** to `demo_user role=user`, `verify_artifact` passes again with the same `artifact_sha256 48ce02563b2aad9f…`, health is `ok`, the probe session is revoked, and `docker inspect` shows `{"2026/tcp":null}`. |
| `extract_matrix.py` | The script that turns the raw transcript into the matrix table and fails on an unproven citation. |
| `restart.sh` | The T11 deployment probe above. Credentials come from the container's own environment; the session token lives in a `mktemp` file with mode 600 and is removed by an `EXIT` trap. |
| `probe_http.py` | The live HTTP/WebSocket probe. Standard library only, so the result does not depend on host tooling. |
| `probe_logs.py` | The log scan. It names the *variable* that leaked, never its value. |

## What was added in this sprint

`tests/test_integration.py` (T01, T11, T12 — the journeys that only exist end to end) and
`tests/test_adversarial.py` (the 14-function RBAC sweep, the 10 MiB boundary at exactly
`max_bytes` and `max_bytes + 1`, quarantine containment against a traversal name, the
secret-pattern scan over every shipped file, "the database is not a static file", "no
credential in a log record", XSRF/CORS). Together: 22 cases, taking the suite from 263 to 285.

## Re-running the checks

```bash
cd /home/ec-user/non_prod/hafyz_ds
docker run --rm -v "$PWD:/app:z" -w /app aihubcampus-web:local \
    python -m pytest tests -v -p no:cacheprovider > evidence/s11/test-results/pytest_all_verbose.txt 2>&1
python3 evidence/s11/extract_matrix.py > evidence/s11/test-results/t_matrix_extract.txt
python3 evidence/s11/probe_http.py https://www.aihubcampus.online > evidence/s11/probe_http.txt 2>&1
python3 evidence/s11/probe_logs.py aihubcampus-web-1 > evidence/s11/probe_logs.txt 2>&1
bash evidence/s11/restart.sh > evidence/s11/restart.txt 2>&1
python3 scripts/check_no_secrets.py > evidence/s11/test-results/check_no_secrets.txt 2>&1
```

`restart.sh` recreates the deployed `web` container. That is the point of the check, and it is
the only stack this sprint touches.
