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
├── app.py                     # Streamlit entry point — branded shell + inert sign-in (S1)
├── src/config.py              # typed, non-secret environment settings (S1)
├── src/validation.py          # CSV + 23-feature validation, quarantine (S2)
├── ml/schema.py               # the 25-column / 23-feature contract, single source (S2)
├── ml/generate_eda.py         # six EDA figures + descriptive summary from the CSV (S3)
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
│                              #   report evidence, preprocessing contract (S3)
├── evidence/s0/ … evidence/s3/ # captured command output
├── ml/                        # schema.py, inspect_dataset.py, verify_draft_claims.py
├── tests/                     # pytest: settings, login shell (S1), schema/validation (S2)
└── models/eda/                # six committed EDA PNGs + summary.json (S3);
                               #   metrics.json and the pipeline arrive in S4–S5
```

Modules are added when the sprint that implements them runs — no dead placeholder files.
`db.py`, `security.py`, `inference.py` and the page modules arrive with S6–S9.

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

## Documentation index

| Doc | Read it for |
|---|---|
| `docs/source_of_truth.md` | Which source wins when two disagree; the conflict register |
| `docs/rubric_matrix.md` | Every marked item mapped to the sprint that produces its evidence |
| `docs/architecture.md` | Components, topology, tech choices, ingress port decision, threat model |
| `docs/data_dictionary.md` | Every column, its unit (NTD), month, code meanings, constraints and rejection codes |
| `docs/report_evidence.md` | What is verified by code today vs still `claimed` from the drafts |
| `docs/preprocessing_contract.md` | The split, transform and artifact contract S4 must implement (S3) |

## Next sprint

**S4** — three-model training and fair evaluation: `ml/train.py`, `ml/evaluate.py`, three
metrics/confusion-matrix records and the `claimed` vs `reproduced` comparison table. It
implements exactly the contract in `docs/preprocessing_contract.md`: stratified 80/20 split
with `random_state=42`, `ColumnTransformer` fitted on the training rows only, Logistic
Regression scaled, the tree models unscaled, one final held-out test pass.
