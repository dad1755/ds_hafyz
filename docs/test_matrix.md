# Test matrix — T01–T12, expected vs observed

Sprint 11 (blueprint §9). Every row below names the command or test id that exercises the
requirement, what the requirement *expects*, and what the run actually produced. Nothing here
is a plan: each **Observed** cell quotes output that exists under `evidence/`, and the raw
pytest transcript is kept verbatim so the quotes can be checked.

| | |
|---|---|
| Run date | 2026-10-27, Asia/Kuala_Lumpur (+08) |
| Tree | `/home/ec-user/non_prod/hafyz_ds`, branch `s11/testing-verification` |
| Image | `aihubcampus-web:local` (Python 3.12.14, pytest 9.1.1, pluggy 1.7.0) |
| Command | `docker run --rm -v "$PWD:/app:z" -w /app aihubcampus-web:local python -m pytest tests -v -p no:cacheprovider` |
| Result | **285 passed in 598.66s (0:09:58)** — 0 failed, 0 error, 0 skipped |
| Raw transcript | `evidence/s11/test-results/pytest_all_verbose.txt` (finished 2026-10-27 07:14:34 +08) |
| Machine check of this table | `evidence/s11/test-results/t_matrix_extract.txt` — `RESULT: PASS — every cited test id appears in the raw run as PASSED (12 requirements, 285 executed test cases)` |

The suite grew from 263 tests at S10 to **285** here: 22 new cases in `tests/test_integration.py`
(the three cross-cutting journeys, T01/T11/T12) and `tests/test_adversarial.py` (the sweep,
the size boundary, quarantine containment, the secret scan, the log scan, XSRF/CORS).

## T01–T12

| ID | Expected | Command / test id | Observed | Evidence |
|---|---|---|---|---|
| **T01** | A valid admin and a valid user both sign in through the real page, and each is served a *different* view. | `pytest tests/test_integration.py::test_t01_an_admin_and_a_user_sign_in_to_different_navigation tests/test_app_auth.py::test_an_admin_signs_in_and_sees_the_admin_section tests/test_app_auth.py::test_a_regular_user_never_sees_the_admin_section -q` | PASSED. Admin navigation is exactly `Home, Predict default risk, My prediction history, User management, Dataset manager, Model evaluation`; the user's is exactly the first three. Both sessions are database rows, and the page states `Signed in as …` with `Role \`admin\`` / `Role \`user\`` respectively. | `pytest_all_verbose.txt` (3 node ids), `evidence/s11/test-results/t_matrix_extract.txt` |
| **T02** | Wrong credentials are refused with one generic message; repeated failures are throttled; the lock lifts by itself. | `pytest tests/test_security.py::test_wrong_password_is_rejected_with_a_generic_message tests/test_security.py::test_five_failures_lock_the_username_even_for_the_right_password tests/test_security.py::test_the_lock_expires_by_itself tests/test_app_auth.py::test_a_wrong_password_shows_one_generic_error_and_opens_no_session -q` | PASSED. The 5th failure (`security.THROTTLE_MAX_FAILURES = 5`) locks the username for `THROTTLE_LOCKOUT = 15 min` **even when the correct password is then supplied**; `retry_after_seconds > 0` and the public message says "minute". A different username is unaffected, and after `lockout + 1 s` the correct password signs in again. The page opens no session on a bad password. | `pytest_all_verbose.txt` (4 node ids) |
| **T03** | A user is barred from the admin screen **and** from the privileged functions behind it. | `pytest tests/test_adversarial.py -k "privileged or sweep or history_cannot" -q` and `pytest tests/test_admin.py -k "user_never_sees or user_calling_an_admin" -q` | PASSED. A 14-entry sweep calls every privileged function in `src.accounts` and `src.data_manager` with a user token: each raises `PermissionDenied`, each writes an `auth.denied` audit row (`denied_after - denied_before == len(PRIVILEGED_CALLS)`), and `users` row 1 is still `('admin', 1)` afterwards. The same sweep with `None` and with a forged token raises `SessionInvalid`. A guard test asserts the sweep list is ≥ 14 entries and contains `accounts.list_users` and `data_manager.stage_upload`, so it cannot pass by iterating over nothing. The user's page renders no management section. | `pytest_all_verbose.txt`, `evidence/s11/test-results/t_matrix_extract.txt` |
| **T04** | An admin adds and edits a user, and the change persists. | `pytest tests/test_admin.py -k "creates_an_account or display_name_edit or role_change_persists" -q` | PASSED. The account created in the UI signs in afterwards; a display-name edit and a role change are each read back from SQLite in a fresh connection and each leave an audit row. | `pytest_all_verbose.txt` |
| **T05** | A valid 25-column CSV is accepted and staged, with counts shown. | `pytest tests/test_admin.py -k "seed_csv_validates or stages_an_upload" -q` | PASSED. The real `data/UCI_Credit_Card.csv` stages as `record_count 30000`, `column_count 25`, `class_zero 23364`, `class_one 6636`, `sha256 a0f0ab49d6326671…`, status `validated`, **`is_active False`** and `active_version is None` (staging activates nothing). The preview is aggregates only — one row per column, `AGE` min/max `(21, 79)` — and the object has no `records` attribute at all. | `pytest_all_verbose.txt` |
| **T06** | A missing-column or malformed CSV is rejected with a clear reason. | `pytest tests/test_admin.py -k "missing_column_upload or wrong_target_upload or lists_a_rejection" -q` and `pytest tests/test_schema.py::test_missing_column_is_rejected_for_that_reason -q` | PASSED. Dropping `PAY_6` yields code `missing_column` and the persisted reason `missing required column(s): PAY_6; …`, no `dataset_versions` row, one `dataset_rejections` row, a `dataset.rejected` audit event, and the quarantined copy removed. A target value `2` yields `invalid_target_value` with "value(s) other than 0 or 1". The page lists the refusal with its reason. | `pytest_all_verbose.txt` |
| **T07** | A valid 23-field submission returns a genuine class, probability and advice. | `pytest tests/test_prediction_ui.py -k "23_contract_features or on_screen_result" -q` | PASSED. The form offers exactly the contract's 23 features in order. The synthetic demonstrator, scored by the shipped artifact, gives **class `1` ("Predicted default next month"), probability `0.7195348837209302`, band `High`, model version `aihubcampus-default-risk-1+48ce02563b2a`**, advice "Offer supportive contact and discuss potential payment arrangements." The page prints the class, the probability to two decimals with *(estimated, uncalibrated)*, the band, the model version and all three disclosures; the stored `prediction_logs` row carries the same class, `pytest.approx(…, abs=1e-12)` probability, tier and version. | `pytest_all_verbose.txt`; the same numbers reproduced directly: `evidence/s11/test-results/demo_prediction.txt` |
| **T08** | Invalid age/limit/codes and missing numeric values are rejected. | `pytest tests/test_prediction_ui.py::test_invalid_input_blocks_the_model_with_a_readable_message tests/test_prediction.py::test_invalid_input_never_reaches_the_model tests/test_schema.py -k "feature_validator_rejects" -q` | PASSED. Clearing `LIMIT_BAL` produces exactly one error — `feature 'LIMIT_BAL' has no value` — with "rejected before the model was called", **no** prediction panel and **0** rows written. The service refuses before the pipeline is invoked, and the validator refuses a missing feature, an unknown key, an unsupported code, an out-of-band value, a non-finite value and a boolean. | `pytest_all_verbose.txt` |
| **T09** | The app's class and probability match the standalone pipeline exactly. | `pytest tests/test_prediction.py -k "service_matches or cli_agrees" -q` and `pytest tests/test_prediction_ui.py::test_the_on_screen_result_equals_the_direct_pipeline_output -q` | PASSED over **6 distinct synthetic rows**: `result.probability` is bit-identical to the direct pipeline (`repr()` compared, not a tolerance) and the class equals `int(probability >= threshold)` with threshold `0.5`. The CLI path agrees too, and the page's rendered numbers equal the pipeline's for the same row. | `pytest_all_verbose.txt`; the S5 CLI-vs-pipeline trace remains at `evidence/s5/cli_vs_pipeline.txt` |
| **T10** | The tier mapping and the textual recommendation match the score boundaries. | `pytest tests/test_prediction.py -k "cutoffs or continuous or between_two_bands" -q` | PASSED. The documented cutoffs `0.25 / 0.50 / 0.75` belong to the **upper** band (`0.25 → watch`, `0.50 → high`, `0.75 → critical`); the 9 edge cases `0.0, 0.2499, 0.25, 0.4999, 0.50, 0.7499, 0.75, 0.9999, 1.0` map to `low, low, watch, watch, high, high, critical, critical, critical`; and a 10,001-point sweep from 0.0 to 1.0 matches **exactly one** band at every point, never skips a band and never goes backwards. Advice text is read from the band object, not retyped by the page. | `pytest_all_verbose.txt` |
| **T11** | A restart keeps the SQLite data, the model and protected access. | `pytest tests/test_integration.py::test_t11_a_restart_keeps_the_database_the_session_and_the_model tests/test_security.py::test_the_database_survives_a_restart -q` — and at deployment level `bash evidence/s11/restart.sh` | PASSED, twice. *(test)* A **second process** resolves the pre-restart session token to `journey_user / role=user` and re-verifies the model, reporting the same `model_version` and a 64-hex `artifact_sha256`. *(deployment)* `docker compose up -d --force-recreate web` recreated `aihubcampus-web-1` (`started=2026-10-26T23:19:25Z`, `healthy` after 8 polls); row counts were `users 2, sessions 4→5, prediction_logs 0, dataset_versions 1, audit_events 14→16` across the restart; the token issued **before** the restart still resolved afterwards to `demo_user role=user`; `ml.verify_artifact` passed all 11 checks with `artifact_sha256 48ce02563b2aad9f…` before **and** after; `/_stcore/health` → `ok`; `docker inspect` shows `{"2026/tcp":null}` — no published host port. | `evidence/s11/restart.txt`, `pytest_all_verbose.txt` |
| **T12** | The full user journey — login → prediction → history → logout — works. | `pytest tests/test_integration.py -k "t12" -q` | PASSED. One session signs in, submits the 23 fields, sees the result panel, finds its row on the history page, signs out and lands on the sign-in form again; the session is revoked in the database and the prediction row **still exists** afterwards. The companion test proves the same journey cannot start before signing in. | `pytest_all_verbose.txt` |

## Additional adversarial checks (blueprint §9, second paragraph)

| Check | Expected | Command / test id | Observed | Evidence |
|---|---|---|---|---|
| RBAC enforcement | Every privileged entry point refuses a non-admin, and the refusal is audited | `pytest tests/test_adversarial.py -k privileged -q` | PASSED — 14 functions, user token and anonymous caller, `PermissionDenied` / `SessionInvalid`, one `auth.denied` row each | `pytest_all_verbose.txt` |
| File-size limit, exact boundary | 10 MiB accepted, 10 MiB + 1 byte refused | `pytest tests/test_adversarial.py -k "size_limit or exactly_the_limit or quarantine_holds" -q` | PASSED — `validation.MAX_UPLOAD_BYTES = 10 * 1024 * 1024 = 10485760`; a payload of exactly `max_bytes` is accepted, `max_bytes + 1` is refused, and the quarantine path holds the same boundary. `3 passed, 15 deselected` — the boundary case itself (`test_a_payload_of_exactly_the_limit_is_accepted_and_one_byte_more_is_refused`) is selected. (Gate finding F-1: the row originally quoted `exact_the_limit`, which is *not* a substring of `exactly_the_limit`, so the quoted command deselected the very case it was about; corrected here.) | `pytest_all_verbose.txt`, `f1_k_selection.txt` |
| Upload quarantine | An uploaded name is a label, never a path; the stored file is system-named and owner-only | `pytest tests/test_adversarial.py -k quarantine -q`, `pytest tests/test_schema.py -k quarantine -q` | PASSED — a traversal name (`../../etc/passwd`) cannot escape the directory, the stored name is generated (≠ the uploaded name), mode `0600`, names are unique, and an oversize upload leaves no file behind | `pytest_all_verbose.txt` |
| Secret-pattern scan of tracked files | Zero hits for operator secrets and credential patterns | `python3 scripts/check_no_secrets.py` and `--all-files`; also `pytest tests/test_adversarial.py -k "credential_pattern or password_hash or env_example" -q` | PASSED — `PASS — no operator secret and no credential pattern in any tracked file`, exit 0 in both modes at HEAD. The counts recorded in `check_no_secrets.txt` (255 tracked / 264 all-files) were captured before the S11 evidence itself was committed; the gate re-ran the scan at HEAD and got **271 / 271**, still zero hits (finding F-3 — the counts are stale, not wrong). The pytest guard applies the same regexes to every shipped file, refuses a real Argon2 hash in the tree, and asserts `.env.example` carries placeholders only. | `evidence/s11/test-results/check_no_secrets.txt`, `docs/acceptance/S11.md` §4, `pytest_all_verbose.txt` |
| The database is not reachable as a static file | No request can fetch the SQLite file or the dataset/model | `python3 evidence/s11/probe_http.py https://www.aihubcampus.online` | PASSED — `/storage/aihubcampus.db`, `/app/storage/aihubcampus.db`, `…-wal`, `/data/UCI_Credit_Card.csv`, `/models/best_pipeline.joblib` and `/.env` all return the SPA's `text/html` shell (HTTP 200, 4096 bytes) and **none** contains the `SQLite format 3\0` header; the check inspects the body, because a status code alone would lie. | `evidence/s11/probe_http.txt` |
| Model artifact verify | The shipped artifact is the one trusted code produced and scores deterministically | `docker compose exec -T web python -m ml.verify_artifact --models-dir models` | PASSED — 11 checks: checksum, provenance, dataset identity, 23-feature contract, class semantics (threshold 0.5), pickle allowlist (11 classes), pipeline schema, deterministic self-check (0.166092 twice), metrics consistency | `evidence/s11/restart.txt` |
| No secrets in logs | No password, token, hash or key block in the container log | `python3 evidence/s11/probe_logs.py aihubcampus-web-1` | PASSED — 9 lines / 611 bytes scanned against the 4 real operator secrets (used as needles, never printed); no operator secret, no password assignment, no `$argon2…` hash, no key block | `evidence/s11/probe_logs.txt` |
| CSRF / CORS / WebSocket through the proxy | XSRF enforced, foreign origins refused, real-origin upgrade accepted | `python3 evidence/s11/probe_http.py https://www.aihubcampus.online`; `pytest tests/test_adversarial.py -k csrf -q` | PASSED — `_streamlit_xsrf` issued with `SameSite=Lax`, `Path=/`; `Access-Control-Allow-Origin` is absent for `https://evil.example`, `null` and `http://127.0.0.1:2026`; a WebSocket handshake from a foreign origin is **403**, from the real origin **101 Switching Protocols**; the same three results repeat on the apex hostname. The committed `.streamlit/config.toml` is asserted to keep `enableXsrfProtection`/`enableCORS` on, and no code turns them off. | `evidence/s11/probe_http.txt`, `pytest_all_verbose.txt` |

## Acceptance items not in the tables

| Item | Command | Observed | Evidence |
|---|---|---|---|
| Full suite green, count quoted | `python -m pytest tests -v -p no:cacheprovider` | **285 passed in 598.66s (0:09:58)** | `evidence/s11/test-results/pytest_all_verbose.txt` |
| `compileall` clean | `docker run --rm -v "$PWD:/app:z" aihubcampus-web:local sh -c 'cp -r /app/app.py /app/src /app/ml /tmp/ && cd /tmp && python -m compileall -q app.py src ml'` | `compileall exit=0`, 39 `.pyc` files written, no `Error compiling` line | `evidence/s11/test-results/compileall.txt` |
| Secret-pattern scan | `python3 scripts/check_no_secrets.py` | `PASS — no operator secret and no credential pattern in any tracked file.` | `evidence/s11/test-results/check_no_secrets.txt` |

## Honest notes

- **No test failed in this run, so there was no repair cycle in this run.** The suite was green
  on the first execution of the committed tree; every number above comes from that execution,
  not from a later one.
- `compileall` cannot write `.pyc` files into the bind-mounted tree, because the container runs
  as the unprivileged `app` user and the tree belongs to the operator. The command above copies
  the same files into a writable directory inside the container and compiles them there. The
  first attempt, which wrote into the mount, is recorded in the shell history of this sprint as
  a `PermissionError`, not a syntax error.
- T11 is proven twice on purpose: as a unit-level restart (a second process) and as a real
  `docker compose up -d --force-recreate` of the deployed service.
- **This document is the implementer's record, not a verification verdict.** Sprint 11 is
  verified only by the independent gate (a different agent), per blueprint §0. That gate ran at
  `11ae70b` and returned **PASS** with 5 non-blocking findings — see `docs/acceptance/S11.md`.
  F-1 (the file-size row quoted a `-k` term that deselected its own boundary case) and F-3 (the
  recorded secret-scan file counts predate the evidence commit) are corrected in this table;
  F-2, F-4 and F-5 are recorded in the acceptance document and left as they are, because each
  is a strength-of-proof or coverage note rather than an error.

## Sprint 12 — the suite re-run on the digest-pinned base

S12 changed the base image from the moving `python:3.12-slim` tag to a digest. A pinned base is
only worth having if the suite still passes on it, so the whole suite was re-run inside the
rebuilt image as part of the release gate:

```bash
scripts/verify_release.sh --build --with-tests
```

```
PASS  pytest suite  285 passed in 587.26s (0:09:47)
```

Same 285 tests, same result as S11 — the pin changed which bytes the image is built from, not
the behaviour of the code on top of them. The full transcript is `evidence/s12/release_gate.txt`.

S12's own checks are not unit tests: they are the four scripts under `scripts/` exercised against
the live stack, and their transcripts live in `evidence/s12/`. `docs/runbook.md` §7 is the table
of which script answers which question.
