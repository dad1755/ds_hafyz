# 26. Appendices

Draft, Sprint 14. The appendices carry what the body summarises: the data contract, the
configuration surface, the test commands, the code map and the acceptance history.

## Appendix A — Dataset schema (25 columns)

| # | Column | Kind | Unit | Validation |
|---:|---|---|---|---|
| 1 | `ID` | identifier | — | unique; excluded from training and the form |
| 2 | `LIMIT_BAL` | amount | NTD | `>= 1`; form band 10,000–1,000,000 |
| 3 | `SEX` | code | — | `{1, 2}` |
| 4 | `EDUCATION` | code | — | `{0,1,2,3,4,5,6}` |
| 5 | `MARRIAGE` | code | — | `{0,1,2,3}` |
| 6 | `AGE` | amount | years | `18 <= AGE <= 100` |
| 7–12 | `PAY_0`, `PAY_2`, `PAY_3`, `PAY_4`, `PAY_5`, `PAY_6` | status code | — | `{-2..9}`; no `PAY_1` exists |
| 13–18 | `BILL_AMT1` … `BILL_AMT6` | signed amount | NTD | finite whole number; negative allowed |
| 19–24 | `PAY_AMT1` … `PAY_AMT6` | amount | NTD | `>= 0` |
| 25 | `default.payment.next.month` | target | — | `{0, 1}`; 1 = default next month |

Full descriptions, observed ranges and code meanings: `docs/data_dictionary.md`. The
machine-readable contract is `ml/schema.py`.

## Appendix B — Configuration surface (names only)

The application reads its settings from the environment. Only names are listed here; no value is
recorded in this repository.

| Variable | Purpose |
|---|---|
| `APP_ENV`, `APP_DOMAIN` | Environment name and the hostname the app expects |
| `APP_PORT` | Listening port (2026) |
| `APP_SESSION_SECRET` | Session signing material |
| `APP_DB_PATH` | SQLite file location |
| `APP_QUARANTINE_DIR` | Where an upload is parked under a generated name |
| `DATA_RETENTION_DAYS` | Intended retention window (no purge job yet) |
| `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_PASSWORD` | Seed credentials for the operator admin, used once |
| `INITIAL_USER_USERNAME`, `INITIAL_USER_PASSWORD` | Seed credentials for the demonstration user |
| `TUNNEL_TOKEN` | Cloudflare tunnel token, read from `.env.cloudflared` by the `cloudflared` service |

`.env.example` and `.env.cloudflared.example` carry placeholders only; the real files are git-ignored
and mode 600, and `scripts/check_no_secrets.py` asserts that no operator secret appears in any tracked
file.

## Appendix C — Reproducing the evidence

```bash
# data facts and draft-claim verification
python3 ml/inspect_dataset.py --csv data/UCI_Credit_Card.csv
python3 ml/verify_draft_claims.py --csv data/UCI_Credit_Card.csv

# EDA, training, evaluation, artifact verification
python ml/generate_eda.py --csv data/UCI_Credit_Card.csv --out models/eda
python -m ml.train --csv data/UCI_Credit_Card.csv --out models
python -m ml.evaluate --models-dir models
python -m ml.verify_artifact --models-dir models

# the suite and the release gate
docker run --rm -v "$PWD:/app:z" -w /app aihubcampus-web:local python -m pytest tests -v
scripts/verify_release.sh --build --with-tests
scripts/smoke_test.sh --url https://www.aihubcampus.online
python3 scripts/check_no_secrets.py
```

## Appendix D — Code map

| Area | Files |
|---|---|
| Application shell | `app.py`, `src/config.py`, `src/pages_login.py` |
| Security | `src/security.py`, `src/accounts.py`, `src/audit.py` |
| Data | `src/validation.py`, `src/data_manager.py`, `ml/schema.py` |
| Inference | `src/inference.py`, `src/recommendations.py`, `ml/verify_artifact.py` |
| Pages | `src/pages_prediction.py`, `src/pages_history.py`, `src/pages_admin.py`, `src/pages_datasets.py`, `src/pages_evaluation.py` |
| ML pipeline | `ml/inspect_dataset.py`, `ml/generate_eda.py`, `ml/train.py`, `ml/evaluate.py`, `ml/verify_draft_claims.py` |
| Operations | `scripts/verify_release.sh`, `scripts/smoke_test.sh`, `scripts/backup.sh`, `scripts/restore.sh`, `scripts/check_no_secrets.py`, `scripts/init_admin.py` |
| Tests | `tests/test_security.py`, `tests/test_app_auth.py`, `tests/test_admin.py`, `tests/test_prediction.py`, `tests/test_prediction_ui.py`, `tests/test_evaluation.py`, `tests/test_integration.py`, `tests/test_adversarial.py`, `tests/test_schema.py` |

## Appendix E — Acceptance history

Each sprint below has an independent acceptance record written by a different agent identity from
the implementer. The verdicts are the gate's, not the author's.

| Sprint | Record | Verdict |
|---|---|---|
| S0 | `docs/acceptance/S00.md` | PASS, no blocking defect |
| S1 | `docs/acceptance/S01.md` | PASS |
| S2 | `docs/acceptance/S02.md` | PASS |
| S3 | `docs/acceptance/S03.md` | PASS |
| S4 | `docs/acceptance/S04.md` | PASS |
| S5 | `docs/acceptance/S05.md` | PASS |
| S6 | `docs/acceptance/S06.md` | PASS |
| S7 | `docs/acceptance/S07.md` | PASS |
| S8 | `docs/acceptance/S08.md` | PASS |
| S9 | `docs/acceptance/S09.md` | PASS, 6 findings none blocking |
| S10 | `docs/acceptance/S10.md` | PASS, 7 findings none blocking |
| S11 | `docs/acceptance/S11.md` | PASS, 5 findings none blocking |
| S12 | `docs/acceptance/S12.md` | PASS after one blocking finding was fixed |
| S13 | `docs/acceptance/S13.md` | PASS at `49540a6`, 3 findings (F-1, F-2, F-3) recorded and unfixed |

S14 (this report and rubric evidence) has no gate record at the time of writing; that is the next
step, and this draft does not certify itself.

## Appendix F — Figure and table index

See `docs/report/00_figure_table_inventory.md` for every figure and table with its caption, its file
and the file its numbers come from.

## Evidence

- `docs/data_dictionary.md`
- `ml/schema.py`
- `.env.example`
- `.env.cloudflared.example`
- `scripts/check_no_secrets.py`
- `docs/acceptance/S00.md`
- `docs/acceptance/S13.md`
- `docs/report/00_figure_table_inventory.md`
- `docs/rubric_matrix.md`
