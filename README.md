# AI Hub Campus — Credit Card Default Risk Prediction

Academic decision-support web application: a signed-in user submits 23 historical
attributes of a credit-card account and receives a predicted next-month default
probability, a display tier and supportive recommendations. Admin and User roles.
Streamlit + scikit-learn + SQLite in Docker, published through an existing Cloudflare
Tunnel at **www.aihubcampus.online**.

> **Status: Sprint 0 complete, awaiting independent verification.** Only discovery,
> dataset verification and documentation exist. There is no application code, no trained
> model, no container and no deployment yet. Anything claiming otherwise is unverified.

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

## Repository layout (target)

```text
.
├── README.md                  # this file
├── blueprint.md               # implementation specification, S0–S16
├── Group Project 40%.md       # assessment authority (report + presentation rubric)
├── data/UCI_Credit_Card.csv   # immutable benchmark seed
├── docs/
│   ├── source_of_truth.md     # precedence rules + conflict register
│   ├── rubric_matrix.md       # 26 report components + 9+9 rubric items → sprints
│   ├── architecture.md        # topology, tech choices, ingress, threat model
│   └── report_evidence.md     # verified vs claimed, discrepancies, limitations
├── evidence/s0/               # captured Sprint 0 command output
├── ml/                        # inspect_dataset.py, verify_draft_claims.py (S0)
│                              # + schema.py, eda, train, evaluate (S2–S5)
├── src/                       # app logic: auth, validation, inference (S2–S9)
├── models/                    # artifacts + metrics.json (S4–S5)
└── app.py                     # Streamlit entry point (S1)
```

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

## Security and scope rules

- Secrets live only in the operator's `.env` / `.env.cloudflared` (mode 600, git-ignored).
  No credential is committed, logged, echoed or screenshotted. `.env.example` will carry
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

## Documentation index

| Doc | Read it for |
|---|---|
| `docs/source_of_truth.md` | Which source wins when two disagree; the conflict register |
| `docs/rubric_matrix.md` | Every marked item mapped to the sprint that produces its evidence |
| `docs/architecture.md` | Components, topology, tech choices, ingress port decision, threat model |
| `docs/report_evidence.md` | What is verified by code today vs still `claimed` from the drafts |

## Next sprint

**S1** — repository skeleton, pinned dependencies, `.env.example`, `.streamlit/config.toml`,
Dockerfile, Compose, static login shell and health endpoint on port 2026. No model, no
auth logic yet.
