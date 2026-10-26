# AI Hub Campus — Credit Card Default Risk Prediction

Academic decision-support web application: a signed-in user submits 23 historical
attributes of a credit-card account and receives a predicted next-month default
probability, a display tier and supportive recommendations. Admin and User roles.
Streamlit + scikit-learn + SQLite in Docker, published through an existing Cloudflare
Tunnel at **www.aihubcampus.online**.

> **Status: Sprint 3 complete, awaiting independent verification.** The container from S1
> builds and serves; the 25-column data contract, the CSV validator, the upload quarantine
> and the 23-feature request validator are implemented and tested against the seed file; the
> six EDA figures are generated from the CSV by `ml/generate_eda.py` and the preprocessing
> contract S4 must implement is fixed in `docs/preprocessing_contract.md`.
> There is still **no authentication, no database, no model, no dataset activation and no
> deployment** — nothing on the page authenticates anyone or scores anything, and the app
> is not reachable from the internet.

## Data provenance and citation

The dataset is the public **Default of Credit Card Clients** dataset. It is historical,
pseudonymous and **not** live bank data.

- UCI Machine Learning Repository, dataset 350 —
  <https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients>.
  Repository citation: *Yeh, I. (2009). Default of Credit Card Clients [Dataset].
  UCI Machine Learning Repository.* <https://doi.org/10.24432/C55S3H>
- Yeh, I.-C. & Lien, C.-H. (2009). *The comparisons of data mining techniques for the
  predictive accuracy of probability of default of credit card clients.*
  Expert Systems with Applications, 36(2), 2473–2480.
  <https://doi.org/10.1016/j.eswa.2007.12.020>
- Population: credit-card clients of a **Taiwanese** bank, billing months April–September
  **2005**. Monetary amounts are in **New Taiwan Dollars (NTD)**.
- Local copy: `data/UCI_Credit_Card.csv`, SHA-256
  `a0f0ab49d6326671d6cd83be5c88dcf18007025fe9a53ecd699119c871176ca1` (verified in Sprint 0).

The dataset is used unmodified. No record in it is edited, and no value is inferred or
filled.

### Verified dataset facts

Produced by `python3 ml/inspect_dataset.py` (full output: `evidence/s0/inspect_dataset.txt`):

| Fact | Value |
|---|---|
| Rows × columns | 30,000 × 25 |
| Predictors used by the model | **23** (`ID` and the target are excluded) |
| Missing cells | 0 |
| Duplicate full rows | 0 |
| Class 0 — no default next month | 23,364 (77.88%) |
| Class 1 — default next month | 6,636 (22.12%) |
| Metadata checksum (dataset-version identity) | `ceae980f66ed32281e669b2d3dfd67c6e5cbba973f0c10637187d5f591bb8a27` |

## Repository layout (current)

```text
.
├── README.md                  # this file
├── blueprint.md               # implementation specification, S0–S16
├── Group Project 40%.md       # assessment authority (report + presentation rubric)
├── app.py                     # Streamlit entry point — sign-in, session, navigation and the
│                              #   signed-in home page (S6/S7); loads the verified model (S5)
├── src/config.py              # typed, non-secret environment settings (S1)
├── src/validation.py          # CSV + 23-feature validation, quarantine (S2)
├── src/inference.py           # verified, cached, read-only prediction service (S5)
├── src/recommendations.py     # the four documented risk bands (S5)
├── src/db.py                  # SQLite connection policy + idempotent migrations (S6)
├── src/security.py            # Argon2id, password policy, throttle, sessions, role guard (S6)
├── src/audit.py               # append-only, non-sensitive audit events (S6)
├── src/accounts.py            # guarded account administration + last-admin rule (S6)
├── src/predictions.py         # guarded prediction log: own rows only, one row per request (S7)
├── src/pages_login.py         # sign-in and forced password change (S7)
├── src/pages_prediction.py    # the 23-input form, validation, result panel (S7)
├── src/pages_history.py       # the signed-in account's own prediction history (S7)
├── scripts/init_admin.py      # one-time operator seeding from the environment (S6)
├── ml/schema.py               # the 25-column / 23-feature contract, single source (S2)
├── ml/generate_eda.py         # six EDA figures + descriptive summary from the CSV (S3)
├── ml/train.py, ml/evaluate.py # three-model training, fair evaluation, artifact (S4)
├── ml/verify_artifact.py      # eleven ordered checks on the shipped artifact (S5)
├── .streamlit/config.toml     # server address/port 2026, CORS + XSRF on (S1)
├── Dockerfile                 # python:3.12-slim, non-root, healthcheck (S1)
├── compose.yaml               # project `aihubcampus`: web + cloudflared, no host ports (S1)
├── requirements.in            # direct dependencies (human-edited)
├── requirements.txt           # fully pinned lock, 54 entries (generated)
├── .env.example               # placeholders only
├── .env.cloudflared.example   # tunnel-token placeholder only
├── .dockerignore
├── data/UCI_Credit_Card.csv   # immutable benchmark seed
├── docs/                      # architecture, data dictionary, source of truth, rubric matrix,
│                              #   report evidence, preprocessing + inference contracts
├── evidence/s0/ … evidence/s8/ # captured command output
├── ml/                        # schema.py, inspect_dataset.py, verify_draft_claims.py
├── tests/                     # pytest: settings (S1), schema/validation (S2), model contract
│                              #   + prediction (S5), security + app auth (S6), prediction log
│                              #   + prediction UI (S7), admin user management (S8)
└── models/                    # best_pipeline.joblib, metrics.json, model_manifest.json (S4/S5),
                               #   figures/ and eda/ committed evidence (S3/S4), candidates/
```

Modules are added when the sprint that implements them runs — no dead placeholder files.
The dataset manager and the evaluation panels arrive with S9–S10.

## Sprint 0 commands (run today, no dependencies)

```bash
python3 ml/inspect_dataset.py --csv data/UCI_Credit_Card.csv
python3 ml/verify_draft_claims.py --csv data/UCI_Credit_Card.csv
```

Both scripts are standard-library only (no pandas, no network), exit non-zero when the
data disagrees with the documented contract, and regenerate `evidence/s0/*.txt`.

`verify_draft_claims.py` exits 1 by design: it reports **one genuine error** in draft v3
(the `EDUCATION` "others" default rate is 5.7% for code 4 alone, not the 7.05% aggregate
of codes 0,4,5,6). See `docs/report_evidence.md` §4.

## Sprint 1 — build and run the container

```bash
cp .env.example .env && chmod 600 .env     # replace every REPLACE_WITH_* value
docker compose config --quiet              # validation only; never print expanded env
docker compose build web
docker compose up -d web
docker compose ps                          # STATUS must show (healthy); PORTS must show 2026/tcp only
docker compose exec -T web python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:2026/_stcore/health').status)"
docker compose exec -T web python -c "import urllib.request; print(urllib.request.urlopen('http://web:2026/_stcore/health').status)"   # the exact ingress target
docker compose down                        # never `down -v`
```

`cloudflared` is **not** started by these commands and needs no token to exist. When the
tunnel is eventually started (S13) it reads `TUNNEL_TOKEN` from `.env.cloudflared` — see
`.env.cloudflared.example`.

Tests run inside the built image, so they use the pinned dependencies and no host Python:

```bash
docker run --rm -v "$PWD/tests:/app/tests:ro,z" aihubcampus-web:local python -m pytest tests -q
```

S1 evidence (real command output, nothing hand-written): `evidence/s1/`.

## Security and scope rules

- Secrets live only in the operator's `.env` / `.env.cloudflared` (mode 600, git-ignored).
  No credential is committed, logged, echoed or screenshotted; the example files carry
  placeholders only.
- `scripts/check_no_secrets.py` is the gate: it reads the operator env, scans every
  tracked file (including the `.docx` drafts) and fails on any secret or credential
  pattern. Run it before every commit. `PROJECT_DETAILS.md` (operator record with demo
  credentials) is git-ignored for this reason.
- No public host port. The container is `expose:`d on the internal Docker network only.
- This project writes only inside this directory and runs exactly one Compose project,
  `aihubcampus`. It never touches other stacks, containers, networks, DNS or tunnels.
- The app serves on **2026** to match the existing tunnel ingress — rationale and
  alternatives in `docs/architecture.md` §5.

## Sprint 2 — schema, validation and quarantine

```bash
python -m ml.inspect_dataset --csv data/UCI_Credit_Card.csv   # contract checks + metadata checksum
python -m pytest tests/test_schema.py -q                      # the S2 gate
```

- `ml/schema.py` is the single source of the 25-column file contract, the 23-feature model
  contract, the legal code sets, the documented ranges and the dataset metadata checksum.
  It is standard-library only, so the inspection tool still runs without pandas.
- `src/validation.py` validates a whole CSV (`validate_csv_bytes`, `validate_dataframe`),
  one 23-feature request (`validate_features`) and the quarantine path
  (`quarantine_upload`, `ingest_upload`). Every failure carries a stable code and a message
  that names the column and row count, never a cell value.
- `docs/data_dictionary.md` renders the contract for humans: units (NTD), month mapping
  (`PAY_0` = Sep 2005 … `PAY_6` = Apr 2005), code meanings, constraints and error codes.
- `data/quarantine/` is git-ignored; uploads are stored under a generated name with their
  SHA-256, and the seed CSV is never a destination.

## Sprint 3 — preprocessing design and EDA evidence

```bash
# regenerate all six figures and the descriptive summary from the CSV alone
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl \
  -v "$PWD:/app:z" -w /app aihubcampus-web:local \
  python ml/generate_eda.py --csv data/UCI_Credit_Card.csv --out models/eda
```

- `ml/generate_eda.py` writes exactly six figures — class distribution, age by class, credit
  limit by class, default rate by `PAY_0`, default rate by `EDUCATION`, financial correlation
  heatmap — plus `models/eda/summary.json`. Two runs produce byte-identical files
  (`evidence/s3/eda_determinism.txt`).
- The figures are 750 px wide (940 px for the heatmap), i.e. 2× a 375 px viewport, with titled
  axes, the unit in the axis label (NTD / years / %), a code legend where the axis shows codes,
  and a source line.
- `docs/report_evidence.md` §6 carries the class counts, the descriptive-statistics table and
  one substantive, causally-neutral caption per figure, with the sample size behind each
  number. Small categories (`EDUCATION` 0/4/5/6, `MARRIAGE` 0, `PAY_0` 4–8) are flagged as
  unstable rather than interpreted.
- `docs/preprocessing_contract.md` fixes what S4 implements: stratified 80/20 split with
  `random_state=42`, `ColumnTransformer` fitted on train only, scaled Logistic Regression,
  unscaled tree models, no one-hot on the codes (documented limitation), threshold 0.5, one
  saved pipeline at inference.
- No model is trained in this sprint, and the seed CSV is byte-unchanged.

## Sprint 5 — model artifact, prediction service, safety mapping

```bash
# the gate: eleven ordered checks on models/best_pipeline.joblib + model_manifest.json
python -m ml.verify_artifact --models-dir models

# one request through the verified, cached service (prints the full result as JSON)
echo '{"LIMIT_BAL": 20000, "SEX": 2, "EDUCATION": 2, "MARRIAGE": 2, "AGE": 24,
       "PAY_0": 3, "PAY_2": 3, "PAY_3": 2, "PAY_4": 2, "PAY_5": 1, "PAY_6": 0,
       "BILL_AMT1": 3913, "BILL_AMT2": 3102, "BILL_AMT3": 689, "BILL_AMT4": 0,
       "BILL_AMT5": 0, "BILL_AMT6": 0,
       "PAY_AMT1": 0, "PAY_AMT2": 0, "PAY_AMT3": 0, "PAY_AMT4": 0,
       "PAY_AMT5": 0, "PAY_AMT6": 0}' | python -m src.inference --input -

python -m pytest tests/test_model.py tests/test_prediction.py -q   # the S5 gate
```

- `ml/verify_artifact.py` fails loudly (exit 1, every failure named) when the artifact is not
  the bytes the manifest records, was not produced by `ml/train.py → ml/evaluate.py`, carries a
  feature order other than `ml.schema.FEATURES`, records a threshold other than 0.5, or
  references any class outside the allowlisted scientific stack. The pickle allowlist and the
  load use the same restricted unpickler, so the check cannot be bypassed by loading another
  way — `src/inference.py` has no other load path.
- `src/inference.py` verifies, then loads once per process (cached), and scores a request by
  validating it with the S2 contract and building a one-row frame in **manifest order**. It
  never trains, never reloads during a request, and takes no path from a request.
- `src/recommendations.py` maps the probability onto the four documented bands as half-open
  intervals — continuous and gapless, with 0.25 / 0.50 / 0.75 belonging to the band above
  them. The bands are illustrative UI cutoffs, never regulatory credit grades, and never an
  automated sanction.
- Every result carries the class label *and* its caveat, the probability label, the band and
  its note, the uncalibrated-probability note, the model's measured false-negative rate, the
  model version and the disclaimer — see `docs/inference_contract.md` §5.
- The image now ships the three model files read-only at `/app/models` (root-owned, mode 644;
  the container runs as `app`), and the S1 shell reports the loaded, verified model version in
  its *Build information* expander. S4's training commands are recorded in
  `evidence/s4/train.txt` and `evidence/s4/evaluate.txt`.
- Acceptance evidence: `evidence/s5/` — `cli_vs_pipeline.txt` (direct pipeline vs service vs
  CLI, six inputs, byte-identical class and probability), `boundaries.txt`, `verify_artifact.txt`,
  `tamper.txt`, `image_artifact.txt`, `app_loads_model.txt`.

## Sprint 6 — SQLite, real authentication, session and role guards

```bash
# once per installation, inside the running container (credentials come from .env):
docker compose exec web python scripts/init_admin.py

# the S6 gate
python -m pytest tests/test_security.py tests/test_app_auth.py -q
```

- `src/db.py` owns the connection policy (WAL, 5 s busy timeout, `foreign_keys=ON`,
  `BEGIN IMMEDIATE` for writes) and the migration ladder — `0001_core_tables`,
  `0002_auth_sessions` — applied once each and recorded in `schema_migrations`. The database
  is `/app/storage/aihubcampus.db` on the `app_storage` volume, so it survives a restart; a
  second `migrate()` applies nothing.
- `src/security.py` hashes with **Argon2id** (`$argon2id$v=19$m=65536,t=3,p=4$…`, random
  16-byte salt per hash) and verifies in constant time; there is no SHA-256 path. Passwords
  for new accounts need 12 characters and must not be on a short denylist. Five failures in
  fifteen minutes lock a username for fifteen minutes, and the lock expires by itself.
- A **session is a row**: `sessions.token_hash` is the SHA-256 of the token, with an absolute
  8-hour expiry and a revocation timestamp. Every privileged call re-reads it, so sign-out,
  expiry and deactivation take effect immediately. Deactivating an account revokes its
  sessions in the same transaction.
- `src/accounts.py` is the admin API (list, get, create, set role, activate/deactivate, reset
  password, read audit). Each function calls `require_role(...)` **first**, so a user session
  calling it directly gets `PermissionDenied` and an `auth.denied` audit row — hiding the
  page is presentation, not the control. The last enabled admin cannot be demoted or
  deactivated.
- `scripts/init_admin.py` seeds `ds_hafyz` (admin) and `demo_user` from `.env`, only when no
  admin exists, never overwriting a password, never printing one. The operator's supplied
  admin password is 7 characters, so that account is seeded with `must_change_password = 1`:
  it can sign in once and do nothing but set a compliant password (architecture §14, D13).
- `app.py` now signs in for real: generic error text, an Argon2 verification even for an
  unknown username (so the form does not time-enumerate), a forced-change screen, a role-aware
  page, sign-out, and an admin section that is itself a guarded read. Nothing typed into a
  form is echoed back.
- Evidence: `evidence/s6/` — `init_admin.txt` (seeded, then idempotent), `schema_and_storage.txt`
  (pragmas, tables, hash prefix and a digest of each hash), `security_smoke.txt` (every control
  firing in the runtime), `restart_persistence.txt` (identical hashes after a container
  restart), `pytest_all.txt`, `clean_checkout.txt`, `check_no_secrets.txt`.

## Sprint 7 — user prediction UI (complete vertical slice)

```bash
# the S7 gate
python -m pytest tests/test_predictions.py tests/test_prediction_ui.py -q

# the acceptance comparison: on screen vs CLI vs loaded pipeline, same 23 values
python evidence/s7/ui_vs_pipeline.py
```

- **The form is the contract.** `src/pages_prediction.py` builds all 23 inputs in the four
  documented groups — Credit profile (5), Repayment history (6: `PAY_0`, `PAY_2…PAY_6`, no
  invented `PAY_1`), Billing amounts (6), Previous paid amounts (6) — inside four accordions,
  and asserts at import that they cover `ml.schema.FEATURES` once each, in contract order. Every
  label, unit, billing month and code meaning is read from `COLUMN_SPECS`; a contract change
  breaks the import rather than silently dropping an input.
- **A demonstrator row, labelled as one.** The *Load synthetic demonstrator example* button
  fills invented round numbers (`DEMO_EXAMPLE`) and says on screen that they are not a row from
  the dataset and not a real customer. Every field stays editable afterwards.
- **Validation happens before the model.** `submit_prediction` calls `validate_features` first,
  so a missing number, an impossible age, a negative limit, an out-of-range code or a
  non-numeric value raises `ValidationError` with a message naming the field, and the model is
  never called. The page renders that message and adds that nothing was scored or recorded.
- **The result panel is `PredictionResult` rendered, not reinterpreted**: class wording and its
  caveat, the probability under the label *estimated, uncalibrated*, the band with its
  supportive advice and the band note, the calibration note, the measured false-negative note,
  the 0.50 threshold, the model version and the disclaimer.
- **A repeat submission is not a second row.** The page keeps a per-session fingerprint of the
  23 values; the same values again return the row already recorded and say so. The 23 values
  are never stored — only class, probability, band, model version and timestamp.
- **History is the account's own.** `src/predictions.list_predictions` filters by the user id
  resolved from the session token inside the query; the function takes no user argument. The
  page states that a row is a model output, not a record that a customer defaulted.
- **Every page checks the session itself.** `app.py` resolves the session from the database on
  every rerun and renders sign-in, forced password change, or one signed-in page; each page
  module re-calls `require_authenticated` before it reads anything, so the dispatch is
  presentation rather than the control.
- Evidence: `evidence/s7/` — `ui_vs_pipeline.txt` (screen, CLI and pipeline agree on class,
  probability and band for the same 23 values), `pytest_s7.txt`, `pytest_all.txt`,
  `browser_check.json` + `form_375px.png`, `result_375px.png`, `history_375px.png`,
  `form_desktop.png`, `result_desktop.png`, `history_desktop.png` (a real Chromium at 375×812
  and 1280×800, zero horizontal overflow on every page), `clean_checkout.txt`,
  `check_no_secrets.txt`, `image_build.txt`, `container_health.txt`.

## Sprint 8 — administrator user management

```bash
# the S8 gate
python -m pytest tests/test_admin.py -q

# the two probes: what the page renders, and what the audit trail holds
python evidence/s8/ui_query.py
python evidence/s8/audit_probe.py
```

- **The page is a view, not the control.** `src/pages_admin.py` calls
  `accounts.*` for every read and every write, and each of those functions re-checks the admin
  role against the database before it does anything. A user who reached the page — or who
  called `accounts.create_user` with their own token — gets `PermissionDenied` and an
  `auth.denied` audit row naming the attempted function.
- **List, create, edit, reset, deactivate.** The account table has no hash column because
  `accounts.UserView` has no hash field: a hash is never read into the page, so it cannot be
  rendered. Creating an account, changing a display name or role, setting a temporary password
  and deactivating/reactivating each write exactly one audited transaction
  (`user.created`, `user.display_name_changed`, `user.role_changed`, `password.reset`,
  `user.deactivated`, `user.activated`).
- **A temporary password is never echoed.** The reset form takes it twice, hashes it, sets
  `must_change_password = 1` and ends the account's open sessions; the success message names the
  account and the fact, never the value. The audit row records
  `{"forced_change": true, "username": …}`.
- **No delete, and no way to orphan the installation.** There is no `delete_user` anywhere and
  no `DELETE FROM users` in `src/`; an account is deactivated instead, which keeps its audit
  history and prediction rows. The last enabled administrator cannot be demoted or
  deactivated — refused inside the write transaction, from the UI as well as the service.
- **A role change applies to the next request, not the next sign-in**, because
  `require_role` re-reads the user row on every call. `tests/test_admin.py` asserts exactly
  that with one unchanged session token.
- Evidence: `evidence/s8/` — `pytest_s8.txt` (25 tests), `pytest_all.txt` (228 tests),
  `ui_query.txt` (the page's own text and table, grepped for `$argon2id$` and both synthetic
  passwords: 0 matches), `audit_probe.txt` (every admin write, the quoted `auth.denied` row,
  and a sweep of all audit details for plaintext and hashes: 0 findings), `browser_check.txt`
  with `admin_375px.png`, `created_375px.png`, `new_user_375px.png` and the desktop set (a real
  Chromium creates an account through the form, then signs in as it, zero horizontal overflow),
  `image_build.txt`, `container_health.txt`, `check_no_secrets.txt`, `clean_checkout.txt`.

## Documentation index

| Doc | Read it for |
|---|---|
| `docs/source_of_truth.md` | Which source wins when two disagree; the conflict register |
| `docs/rubric_matrix.md` | Every marked item mapped to the sprint that produces its evidence |
| `docs/architecture.md` | Components, topology, tech choices, ingress port decision, threat model |
| `docs/data_dictionary.md` | Every column, its unit (NTD), month, code meanings, constraints and rejection codes |
| `docs/report_evidence.md` | What is verified by code today vs still `claimed` from the drafts |
| `docs/preprocessing_contract.md` | The split, transform and artifact contract S4 implements (S3) |
| `docs/inference_contract.md` | The artifact gate, the prediction service, the risk bands and the wording every result must carry (S5) |

## Next sprint

**S8** — administrator user management: list, create, edit, deactivate, change role and reset a
password from the page, with an audit event per action and the last-admin rule enforced in the
same transaction. The guarded API already exists in `src/accounts.py`; S8 adds the screens and
the tests that a user session cannot reach them.
