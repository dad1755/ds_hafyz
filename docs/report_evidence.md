# Report evidence — what is verified, what is claimed

Maintained from Sprint 0 onward. `Group Project 40%.md` is the assessment authority and
`blueprint.md` the implementation spec; this file records which statements in the report
are backed by executed commands and which are still assertions from a draft.

Rule: a number appears in the report as a **result** only when a command in this
repository produced it and the output is archived under `evidence/`. Everything else is
labelled `claimed`.

---

## 1. Input inventory

| # | File | Size | SHA-256 | Type | Role | Status |
|---:|---|---:|---|---|---|---|
| 1 | `blueprint.md` | 55,488 B | `bb9583a329eeee0b0221a740b34dc88ec92fac9fa4fb4948880bee3b7909aa0a` | Markdown spec | Implementation specification, S0–S16 | Read in full; spec, not evidence |
| 2 | `Group Project 40%.md` | 17,809 B | `9cb160ce09d9a5d9142f2a3bef72c86f2407b4f5786985d643d9f8db68f9fc1c` | Markdown brief | **Assessment authority**: 26 report components, Rubric A/B, submission rules | Read in full; mapped in `docs/rubric_matrix.md` |
| 3 | `Credit_Card_Default_Prediction_Project.docx` | 39,784 B | `5c8c9a1e2a4afa95af131c462e368a69eebbab989c002a3d29b39966cb088cdc` | Word draft (v1) | Earlier draft, ~7.3k chars | Text extracted; **draft, not proof** |
| 4 | `Credit_Card_Default_Prediction_Project-v3.docx` | 1,291,939 B | `0680b8826b1352393d68a44c3a1720bbdd239286406849e28eb39f4290473f85` | Word draft (v3) | Detailed draft, ~63k chars, figures + tables | Text extracted; **draft, not proof** |
| 5 | `data/UCI_Credit_Card.csv` | 2,862,995 B | `a0f0ab49d6326671d6cd83be5c88dcf18007025fe9a53ecd699119c871176ca1` | CSV dataset | Immutable benchmark seed | **Verified by code** |
| 6 | `PROJECT_DETAILS.md` | 2,927 B | not committed (git-ignored in S0) | Operator record | Host, tunnel ingress, board mapping, demo accounts | Read for host/ingress facts; **holds plaintext demo credentials, never to be committed** |

Extracted text of both drafts: `evidence/s0/draft_v1_extracted.txt`,
`evidence/s0/draft_v3_extracted.txt` (paragraph text plus table cells, produced by a
stdlib `zipfile` + OOXML reader — no Word needed).

**Both `.docx` files are drafts.** Neither contains a run log, a repository path, a
screenshot of a running deployment, or an artifact checksum. Neither is evidence that
any system exists. Their numbers are treated as `claimed` throughout.

### Draft v1 (short version) — what it asserts

~47 paragraphs, no tables of statistics, no test matrix. Claims: 30,000 UCI records;
80/20 split; LR + DT + RF compared; Decision Tree best at "eighty one point seven
percent" accuracy and "thirty five point four percent" recall; Streamlit UI; SQLite with
admin/user roles; joblib-loaded pipeline; "twelve step testing plan" asserted as
completed; "fourteen day deadline" met; cloud migration listed as future work.

### Draft v3 (long version) — what it asserts

Eight sections plus appendix. Adds: attribute dictionary; Table 7 dtypes; Table 8
descriptive statistics (mean/std/quartiles for 8 columns); six EDA charts; step-by-step
metric arithmetic; Table 9 confusion matrices for three models; Table 10 Decision Tree
feature importances (PAY_0 68.01%, PAY_2 13.77%, …); four-layer architecture; SQLite
schema; SHA-256 password hashing; four risk tiers (0–25/26–49/50–74/75–100%); a
"twelve step system verification" with all tests passing; a four-member work division
and 14-day schedule; references and an appendix.

---

## 2. Verified now (executed in this repository, Sprint 0)

### 2.1 Dataset facts — `ml/inspect_dataset.py`

Command: `python3 ml/inspect_dataset.py --csv data/UCI_Credit_Card.csv`
Output: `evidence/s0/inspect_dataset.txt` (exit 0, all 12 checks PASS).

```text
sha256      : a0f0ab49d6326671d6cd83be5c88dcf18007025fe9a53ecd699119c871176ca1
rows        : 30000
columns     : 25
predictors  : 23 (excluding ID and target)
missing     : 0 cells
dupes       : 0 duplicated full rows (0 groups)
ragged rows : 0
sci-notation: 4262 numeric cells written as 5e+05 (all parse to whole numbers; 0 fractional values)
class 0 (no default next month): 23364 (77.88%)
class 1 (default next month): 6636 (22.12%)
RESULT: ALL CHECKS PASS
```

Verified facts, each matching the blueprint's expectation:

| Fact | Expected | Observed | Match |
|---|---|---|---|
| Rows | 30,000 | 30,000 | yes |
| Columns | 25 | 25 | yes |
| Predictors (excl. `ID`, target) | 23 | 23 | yes |
| Missing cells | 0 | 0 | yes |
| Duplicate full rows | 0 | 0 | yes |
| Class 0 | 23,364 (77.88%) | 23,364 (77.88%) | yes |
| Class 1 | 6,636 (22.12%) | 6,636 (22.12%) | yes |
| SHA-256 | `a0f0ab49…176ca1` | `a0f0ab49…176ca1` | yes |

Ordered column list (exact, index order): `ID, LIMIT_BAL, SEX, EDUCATION, MARRIAGE, AGE,
PAY_0, PAY_2, PAY_3, PAY_4, PAY_5, PAY_6, BILL_AMT1…BILL_AMT6, PAY_AMT1…PAY_AMT6,
default.payment.next.month`. There is **no `PAY_1`** column.

Observed code ranges worth stating in the report (these are the "known legal codes" S2
must enforce, not the blueprint's assumed set):

| Column | Observed | Note |
|---|---|---|
| `SEX` | 1–2 | 2 codes |
| `EDUCATION` | 0–6 (7 codes) | includes undocumented 0, 5, 6 |
| `MARRIAGE` | 0–3 (4 codes) | includes undocumented 0 |
| `PAY_0…PAY_6` | −2…8 | −2/−1 are "no consumption"/"paid in full" markers |
| `BILL_AMT1…6` | negative minima observed (e.g. −339,603) | credit balances are legal; validation must allow them |
| `LIMIT_BAL` | 10,000–1,000,000, 81 distinct values | whole NTD |
| `AGE` | 21–79 | whole years |

### 2.2 Draft claims reproduced — `ml/verify_draft_claims.py`

Command: `python3 ml/verify_draft_claims.py --csv data/UCI_Credit_Card.csv`
Output: `evidence/s0/verify_draft_claims.txt` (**67 of 68 confirmed**, one genuine error).

Confirmed against the CSV (selected; full list in the evidence file):

| Draft claim | Draft value | Recomputed | Verdict |
|---|---|---|---|
| `LIMIT_BAL` mean / std / median | 167,484.32 / 129,747.66 / 140,000 | 167,484.3227 / 129,747.6616 / 140,000 | confirmed |
| `AGE` mean / std | 35.49 / 9.22 | 35.4855 / 9.2179 | confirmed |
| `BILL_AMT1` mean / std / p25 / median | 51,223.33 / 73,635.86 / 3,558.75 / 22,381.50 | identical to 2 dp | confirmed |
| `PAY_AMT1` mean / std / median | 5,663.58 / 16,563.28 / 2,100 | identical to 2 dp | confirmed |
| `LIMIT_BAL` mean by class (0 / 1) | 178,099.73 / 130,109.66 | 178,099.7261 / 130,109.6564 | confirmed |
| Default rate by `PAY_0` = −2,−1,0,1,2,3 | 13.2 / 16.8 / 12.8 / 33.9 / 69.1 / 75.8 % | 13.23 / 16.78 / 12.81 / 33.95 / 69.14 / 75.78 % | confirmed to rounding |
| Default rate by `EDUCATION` = 1,2,3 | 19.2 / 23.7 / 25.2 % | 19.23 / 23.73 / 25.16 % | confirmed to rounding |
| corr(`PAY_0`, target) | 0.32 | 0.3248 | confirmed |
| corr(`BILL_AMT1`, `BILL_AMT2`) | 0.95 | 0.9515 | confirmed |
| Stratified 20% test composition | 4,673 / 1,327 | 4,673 / 1,327 | confirmed |

Default rates by `PAY_0` recomputed (full table, for the S3 chart caption):

| `PAY_0` | −2 | −1 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| n | 2,759 | 5,686 | 14,737 | 3,688 | 2,667 | 322 | 76 | 26 | 11 | 9 | 19 |
| default % | 13.2 | 16.8 | 12.8 | 33.9 | 69.1 | 75.8 | 68.4 | 50.0 | 54.5 | 77.8 | 57.9 |

Default rates by `EDUCATION` recomputed:

| `EDUCATION` | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|---:|
| n | 14 | 10,585 | 14,030 | 4,917 | 123 | 280 | 51 |
| default % | 0.0 | 19.2 | 23.7 | 25.2 | 5.7 | 6.4 | 15.7 |

### 2.3 Draft Table 9 arithmetic — same script, section 3

The published confusion matrices are **internally consistent** and consistent with the
dataset's class balance, i.e. the draft did not fabricate numbers that fail their own
formulas:

```text
model                    n      acc     prec      rec       f1  class1 class0  match
Logistic Regression   6000   0.8077   0.6868   0.2396   0.3553    1327   4673  OK
Decision Tree         6000   0.8172   0.6615   0.3549   0.4620    1327   4673  OK
Random Forest         6000   0.8122   0.6773   0.2879   0.4040    1327   4673  OK
OVERALL: ARITHMETIC CONSISTENT
```

This raises confidence in the draft but **proves nothing about the model**: no artifact,
split seed or run log exists in this repository. The metrics stay `claimed` until S4
reproduces them (`models/metrics.json`), and the report will publish whichever numbers
the reproduction actually produces.

---

## 3. Claimed but NOT verified

| Claim | Source | Why unverified | Sprint that settles it |
|---|---|---|---|
| LR / DT / RF accuracy, precision, recall, F1 (Table 9) | v3 §4.2–4.3 | **Settled in S4**: reproduced from `models/best_pipeline.joblib` and `models/metrics.json`; LR and RF match to four decimals, DT to ~1e-3 — see §7.3 | S4 |
| Decision Tree is the best model | v3 §4.3, v1 §5 | **Settled in S4**: highest cross-validated F1 *and* highest held-out F1 of the three — but it misses 64.4 % of defaulters, so "best" means least-bad; see §7.4–7.5 | S4 |
| Feature importance PAY_0 68.01%, PAY_2 13.77% | v3 Table 10 | **Settled in S4**: reproduced exactly (68.01 % / 13.77 %) from the shipped tree — `evidence/s4/feature_importances.txt` | S4 |
| All 12 system tests pass (T01–T12) | v3 §6.1, v1 §6 | No test files, no recorded output | S11 |
| "Fourteen day" schedule met | v3 §1.4, v1 §7 | Planning assumption; deadline not confirmed by the lecturer | S14/S15 |
| Four-member division of work | v3 §1.4 | Not confirmed by the group | S15 (B8) |
| Passwords hashed with SHA-256 | v3 §5.2 | Not implemented; and the blueprint prohibits bare SHA-256 | S6 |
| Six EDA charts exist | v3 §3 | **Settled in S3**: six figures are regenerated by `ml/generate_eda.py`; the draft's embedded images remain unverified and are not reused — see §6 | S3 |
| Live Cloudflare deployment | operator authorisation | **Settled in S13**: `https://www.aihubcampus.online` and the apex serve the app through the operator's tunnel, no host port published — `evidence/s13/browser_check.txt` (29 checks, PASS), `evidence/s13/smoke_test.txt` (16/16), `evidence/s13/probe_http.txt` | S13 |
| Admin/user modules function | v3 §5.2, §6.1 | No code | S6–S8 |

---

## 4. Discrepancies found in Sprint 0 (report text must be corrected)

| # | Finding | Evidence | Required correction |
|---:|---|---|---|
| E1 | **4,262 monetary cells are in scientific notation** (`5e+05`, etc.): `LIMIT_BAL` 4,150; `PAY_AMT1–6` 16/18/9/11/19/12; `BILL_AMT1–6` 2/3/4/5/8/5. All parse to whole NTD (0 fractional values). | `evidence/s0/inspect_dataset.txt` | Report must not claim a clean all-integer dtype table. State that the export mixes plain and scientific notation and that validation parses numerically, asserting whole-NTD values. |
| E2 | **`EDUCATION` "others" default rate is 5.7% in the draft but that figure is code 4 alone**; the aggregate of codes 0,4,5,6 is **7.05%**. | `evidence/s0/verify_draft_claims.txt`, `MISMATCHES` section; recomputed in S3 — `evidence/s3/eda_run.txt` | Rewrite v3 §3.5: either report code 4 as 5.69% (n=123) or the true aggregate 7.05% (n=468). Both figures are restated with sample sizes in §6.3(e). |
| E3 | Draft says "four main education groups"; the data has **7 codes** (0–6), two of them undocumented by UCI. | same | Say "seven observed codes, two undocumented" and justify the S2 handling decision. |
| E4 | Draft/blueprint naming implies `PAY_1`; the CSV has **no `PAY_1`**. | `evidence/s0/inspect_dataset.txt` | Always write `PAY_0, PAY_2…PAY_6`. |
| E5 | Draft claims SHA-256 password hashing. | v3 §5.2 | Implement Argon2id (S6) and correct the report. |
| E6 | Draft calls cloud hosting "future work" while deployment is authorised now. | v3 §7.2 | Re-scope future work; deployment is S13. |
| E7 | Draft labels class 0 "On Time", implying certainty. | v3 §4.2 | Use "predicted non-default next month". |

None of these required touching the data. The CSV is unchanged and its checksum still
matches `a0f0ab49…176ca1`.

---

## 5. Limitations that must appear in the report

1. **Low positive-class recall.** The draft's own numbers imply ~64.5% of actual
   defaulters are missed by the Decision Tree. This must be discussed, not hidden.
2. **Historical, foreign, small.** Taiwan, 2005, 30,000 accounts, NTD. No claim of
   current or Malaysian applicability.
3. **Uncalibrated tiers.** The four display bands are illustrative UI ranges, not
   validated banking thresholds.
4. **Fairness not proven.** `SEX`, `EDUCATION`, `MARRIAGE`, `AGE` are model inputs. No
   fairness audit has been run; demographic ablation is future work.
5. **Not a decision system.** Supportive guidance only; a human must review before any
   action. No automated credit limit or sanction.
6. **Academic prototype.** Containerised and public, but not certified for real lending.

---

## 6. Sprint 3 — EDA evidence and descriptive statistics

### 6.1 How the six figures were produced

`ml/generate_eda.py` reads only `data/UCI_Credit_Card.csv` and writes six PNGs plus
`models/eda/summary.json` — the machine-produced numbers every caption below quotes.

```bash
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl \
  -v "$PWD:/app:z" -w /app aihubcampus-web:local \
  python ml/generate_eda.py --csv data/UCI_Credit_Card.csv --out models/eda
```

| Fact | Value | Evidence |
|---|---|---|
| Figures written | 6 PNG + `summary.json`, 49,050 / 37,386 / 37,584 / 55,088 / 43,507 / 55,133 / 14,041 B | `evidence/s3/eda_run.txt`, `eda_files.txt`, `evidence/s4/eda_source_line.txt` |
| Source line on every figure | after the S3 gate (finding F-1) the correlation heatmap also carries the source line; blueprint §9 asks for title, axes, source and units on the figure set and figure 06 was the one exception. Dropping `source=False` changed **only** figure 06 (46,373 → 55,133 B); the other five blobs and `summary.json` are unchanged | `evidence/s4/eda_source_line.txt` |
| Regeneration is deterministic | two independent runs into separate directories → all 7 files **byte-for-byte identical** (SHA-256 per file) | `evidence/s3/eda_determinism.txt` |
| Files are real, on disk | a fresh container process decoded all six with Pillow: `PNG 750×610` ×5, `PNG 940×820` ×1, mode RGBA | `evidence/s3/eda_render_after_restart.txt` |
| Legible at 375 px | 750 px wide is 2× the 375 px viewport the app must support (S7/S10); heatmap 940 px | same |
| Seed untouched | `data/UCI_Credit_Card.csv` still `a0f0ab49…176ca1`; `git status data/` empty | `evidence/s3/eda_files.txt` |
| Clean checkout | `git archive HEAD` extracted to an empty directory (no `.git`, no untracked files) and regenerated → all 7 files identical to the committed blobs (7/7) | `evidence/s3/clean_checkout.txt` |
| No model trained | the script imports matplotlib and pandas only — no estimator is constructed | `ml/generate_eda.py` |

### 6.2 Class counts and descriptive statistics

Classes (`evidence/s3/eda_run.txt`):

| Class | Meaning | Count | Share |
|---:|---|---:|---:|
| 0 | no default next month | 23,364 | 77.88 % |
| 1 | default next month | 6,636 | 22.12 % |

Ratio 3.52 : 1. **The always-class-0 baseline therefore scores 77.88 % accuracy** — the
number every S4 model must be compared against, not a result of any model.

Key features, all 30,000 rows, 0 missing cells (amounts in NTD, `AGE` in years; the full
23-feature table is in `models/eda/summary.json`):

| Column | Min | Q1 | Median | Mean | Q3 | Max |
|---|---:|---:|---:|---:|---:|---:|
| `LIMIT_BAL` | 10,000 | 50,000 | 140,000 | 167,484.32 | 240,000 | 1,000,000 |
| `AGE` | 21 | 28 | 34 | 35.49 | 41 | 79 |
| `PAY_0` | −2 | −1 | 0 | −0.02 | 0 | 8 |
| `PAY_2` | −2 | −1 | 0 | −0.13 | 0 | 8 |
| `PAY_3` | −2 | −1 | 0 | −0.17 | 0 | 8 |
| `PAY_4` | −2 | −1 | 0 | −0.22 | 0 | 8 |
| `PAY_5` | −2 | −1 | 0 | −0.27 | 0 | 8 |
| `PAY_6` | −2 | −1 | 0 | −0.29 | 0 | 8 |
| `BILL_AMT1` | −165,580 | 3,559 | 22,382 | 51,223.33 | 67,091 | 964,511 |
| `BILL_AMT6` | −339,603 | 1,256 | 17,071 | 38,871.76 | 49,198 | 961,664 |
| `PAY_AMT1` | 0 | 1,000 | 2,100 | 5,663.58 | 5,006 | 873,552 |
| `PAY_AMT6` | 0 | 118 | 1,500 | 5,215.50 | 4,000 | 528,666 |

Two facts a reader should not misread: **negative bill amounts are real** (a credit balance,
minimum −339,603 NTD) and the `PAY_*` means are negative because −1/−2 are *good* codes
("paid in full" / "no consumption"), not missing values.

### 6.3 The six figures, each with its observation

**(a) `models/eda/01_target_class_distribution.png`** — class balance.
Of 30,000 accounts, 23,364 (77.88 %) did not default next month and 6,636 (22.12 %) did.
The 3.52 : 1 split means a model can reach 77.88 % accuracy by always answering "no
default", so accuracy alone cannot show that a model learned anything; recall and F1 on the
default class are what the S4 comparison must lead with.

**(b) `models/eda/02_age_by_class.png`** — age by class.
Both classes have a median age of 34 (class 0 mean 35.42, class 1 mean 35.73); the
interquartile range is 28–41 years for class 0 and 28–42 for class 1, and the sample maximum
is 79 vs 75. The distributions are similar in this sample. No significance test was run, so
the correct statement is "similar in this sample", never "age has no effect" — and the draft's
claim that age "proves no significant effect" must not be repeated.

**(c) `models/eda/03_limit_bal_by_class.png`** — credit limit by class (NTD).
Accounts that defaulted hold smaller limits: median 90,000 NTD vs 150,000 NTD, lower quartile
50,000 vs 70,000, mean 130,109.66 vs 178,099.73. Whiskers are 1.5×IQR and individual
outliers are not drawn, so the class-0 sample maximum of 1,000,000 NTD is off-plot; the
difference in medians, not the whisker ends, is the observation. A credit limit is granted by
the bank, so this is an association between an assigned limit and observed default, not
evidence that raising or lowering a limit changes default behaviour.

**(d) `models/eda/04_default_rate_by_pay0.png`** — default rate by September repayment status.
The rate rises steeply with delay: 12.81 % at code 0 (revolving credit, n = 14,737), 33.95 %
at 1 month of delay (n = 3,688), 69.14 % at 2 months (n = 2,667), 75.78 % at 3 months
(n = 322). The "good" codes sit lower (13.23 % at −2, n = 2,759; 16.78 % at −1, n = 5,686).
Codes 4–8 have 76, 26, 11, 9 and 19 accounts, and their rates (68.42 %, 50.00 %, 54.55 %,
77.78 %, 57.89 %) bounce with no trend — that instability is a small-sample artefact and must
not be quoted as a finding. The plot shows association only: a late payment is a symptom of
financial stress, not a proven cause of default.

**(e) `models/eda/05_default_rate_by_education.png`** — default rate by education code.
The three populated codes are close: 19.23 % (code 1, graduate school, n = 10,585), 23.73 %
(code 2, university, n = 14,030), 25.16 % (code 3, high school, n = 4,917) — a 5.9
percentage-point spread that is not monotone in "years of schooling" either, since university
sits below high school. The remaining codes are too small to interpret: code 4 (n = 123,
5.69 %), code 5 (n = 280, 6.43 %), code 6 (n = 51, 15.69 %) and code 0 (n = 14, 0.00 %); the
four together are 468 accounts, 1.56 % of the sample, and code 0 has **no** defaults at all.
This also settles discrepancy **E2**: the draft's "others 5.7 %" is code 4 alone, and the
aggregate over codes 0/4/5/6 is 7.05 %.

**(f) `models/eda/06_correlation_heatmap.png`** — Pearson correlation of the 13 financial
columns (`LIMIT_BAL`, `BILL_AMT1–6`, `PAY_AMT1–6`; axes abbreviate to `LMT`, `B1–B6`,
`A1–A6`).
Two blocks are visible. The six statement balances are strongly intercorrelated —
`BILL_AMT1`~`BILL_AMT2` r = +0.952, `BILL_AMT5`~`BILL_AMT6` +0.946, `BILL_AMT4`~`BILL_AMT5`
+0.940, `BILL_AMT1`~`BILL_AMT6` still +0.803 — while the payment amounts form a weak block
(`PAY_AMT1`~`PAY_AMT2` +0.286) and bill-versus-payment links are close to zero
(`BILL_AMT1`~`PAY_AMT1` +0.140). `LIMIT_BAL` correlates only moderately with balances
(+0.285 with `BILL_AMT1`). The practical consequence for S4: the bill columns are largely
redundant, so a linear model's coefficients on them will be unstable and must not be read as
individual effects — while the tree models' feature importances are unaffected by that
redundancy. **Correlation is not causation**: these are co-movements inside one 2005 sample,
and no direction of effect is established.

### 6.4 What the figures do not show

1. No significance testing was run. Every comparison above is descriptive ("in this sample").
2. No causal claim. Correlated inputs and correlated outcomes are not evidence of mechanism.
3. Small categories are unstable and are flagged, not interpreted: `EDUCATION` 0/4/5/6
   (n = 14/123/280/51), `MARRIAGE` 0 (n = 54, 9.26 %), `PAY_0` codes 4–8 (n ≤ 76).
4. `SEX` is not interpreted. It is a model input, but no fairness audit exists and the
   blueprint forbids using it to drive advice; the correlation heatmap deliberately excludes
   it.
5. The data is a historical Taiwanese sample from April–September 2005 in NTD. Nothing here
   transfers to current Malaysian portfolios without new evidence.
6. These plots describe the data, not the model. Per-model performance appears in §7.

## 7. Sprint 4 — three-model training and fair evaluation

### 7.1 How the three models were trained

`ml/train.py` implements `docs/preprocessing_contract.md` and nothing else: the 23 features of
`ml.schema.FEATURES` in that order, `ID` and the target dropped, one stratified 80/20 split at
`random_state=42`, one `Pipeline` per candidate whose first step is a `ColumnTransformer` fitted
on `X_train` alone.

```bash
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl \
  -v "$PWD:/app:z" -w /app aihubcampus-web:local \
  python -m ml.train --csv data/UCI_Credit_Card.csv --out models
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl \
  -v "$PWD:/app:z" -w /app aihubcampus-web:local \
  python -m ml.evaluate --models-dir models
```

Full stdout: `evidence/s4/train.txt` and `evidence/s4/evaluate.txt`.

| Candidate | Numeric treatment fitted on `X_train` | Hyper-parameters |
|---|---|---|
| `LogisticRegression` | `StandardScaler` | `max_iter=1000`, `random_state=42` |
| `DecisionTreeClassifier` | `passthrough` | `max_depth=5`, `random_state=42` |
| `RandomForestClassifier` | `passthrough` | `n_estimators=100`, `max_depth=5`, `random_state=42` |

The scaling difference is deliberate (contract §3.1), not an accident of the code. A tree splits
on order, so a monotone rescaling cannot change the fitted tree; a linear model's coefficients
and solver convergence need comparable scales, because `LIMIT_BAL` spans 10,000–1,000,000 NTD
while the `PAY_*` codes span −2…8. The three candidates are therefore *not* "the same pipeline
with a different last step", and the comparison below is between three fair, leakage-free
pipelines rather than one pipeline and two handicapped copies.

### 7.2 The split, and the evidence it did not leak

`train_test_split(test_size=0.2, stratify=y, random_state=42)` → **24,000 train / 6,000 test**,
class mix 18,691/5,309 and 4,673/1,327. Dataset SHA-256 `a0f0ab49…176ca1`, unchanged.

The scaler check is the one that could catch the classic leak. Fitted on the training rows, its
`mean_` for `LIMIT_BAL` is **167,364.666667** — exactly the training mean — while the whole-dataset
mean is 167,484.322667. Maximum absolute difference from the training mean: **0.0**; from the
full-dataset mean: **195.78**. A transform fitted on all 30,000 rows would have produced the
second number. Quoted in `evidence/s4/contract_checks.txt`.

### 7.3 Claimed vs reproduced

The v3 draft's Table 9 numbers as `claimed/reference`, the held-out numbers this repository
produces as `reproduced`. Threshold 0.5, positive class 1, the same 6,000 rows for all three.

| Model | Metric | Claimed (v3) | Reproduced | Delta |
|---|---|---:|---:|---:|
| Logistic Regression | accuracy | 0.8077 | **0.8077** | 0.0000 |
| | precision | 0.6868 | **0.6868** | 0.0000 |
| | recall | 0.2396 | **0.2396** | 0.0000 |
| | F1 | 0.3553 | **0.3553** | 0.0000 |
| Decision Tree | accuracy | 0.8172 | **0.8172** | 0.0000 |
| | precision | 0.6615 | **0.6611** | −0.0004 |
| | recall | 0.3549 | **0.3557** | +0.0008 |
| | F1 | 0.4620 | **0.4625** | +0.0005 |
| Random Forest | accuracy | 0.8122 | **0.8122** | 0.0000 |
| | precision | 0.6773 | **0.6773** | 0.0000 |
| | recall | 0.2879 | **0.2879** | 0.0000 |
| | F1 | 0.4040 | **0.4040** | 0.0000 |

**The Decision Tree does not reproduce exactly, and the report keeps the reproduced numbers.**
Precision is 0.0004 lower, recall 0.0008 higher, F1 0.0005 higher than the draft. The gap is
three orders of magnitude smaller than the differences between models, so it changes no
conclusion — but it is real and it is stated rather than rounded away.

What the draft did not publish is a seed, a library version or a run log, so exact agreement was
never guaranteed. Two further facts say the draft's numbers were *computed*, not invented: its
test-set composition (4,673/1,327) matches this split exactly, and the draft's Table 10
importances reproduce to the second decimal from the tree shipped here — `PAY_0` **68.01 %**,
`PAY_2` **13.77 %** (`evidence/s4/feature_importances.txt`). The residual Decision Tree gap is
consistent with a different scikit-learn version breaking a split threshold tie differently; it
is **not** proven, and the report does not claim to know its cause.

### 7.4 The three confusion matrices

One figure per model, axes labelled, all four counts printed with their share of the 6,000:
`models/figures/confusion_logistic_regression.png`,
`models/figures/confusion_decision_tree.png`,
`models/figures/confusion_random_forest.png`.

| Model | TN | FP | FN | TP | total | accuracy | precision | recall | F1 | ROC-AUC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Logistic Regression | 4,528 | 145 | 1,009 | 318 | 6,000 | 0.8077 | 0.6868 | 0.2396 | 0.3553 | 0.7076 |
| Decision Tree | 4,431 | 242 | 855 | 472 | 6,000 | 0.8172 | 0.6611 | 0.3557 | 0.4625 | 0.7423 |
| Random Forest | 4,491 | 182 | 945 | 382 | 6,000 | 0.8122 | 0.6773 | 0.2879 | 0.4040 | 0.7665 |
| **always class 0** | 4,673 | 0 | 1,327 | 0 | 6,000 | 0.7788 | 0.0000 | 0.0000 | 0.0000 | — |

Every matrix totals 6,000, and every accuracy/precision/recall/F1 above was re-derived from its
own TN/FP/FN/TP with a maximum absolute difference of **0.0** (`evidence/s4/contract_checks.txt`).

Three things the table says that the draft's prose did not:

1. **The baseline is a serious competitor.** Always answering "no default" scores 77.88 %. The
   best model's accuracy is 81.72 %, i.e. **3.84 percentage points** of genuine signal. Any
   report sentence that calls 81.7 % "high accuracy" without that sentence is misleading.
2. **The best model still misses most defaulters.** The Decision Tree catches 472 of 1,327
   defaulters and misses **855 (64.4 %)**. That is the model's headline risk, not a footnote.
3. **The two tree models trade recall against precision in opposite directions.** The Random
   Forest raises precision (0.6773 vs 0.6611) by cutting false positives 242 → 182, and pays for
   it with 90 more missed defaulters (945 vs 855). Neither is "better" in the abstract; the
   objective in §7.5 is what picks one.

ROC-AUC is reported for all three because all three produce probabilities; the always-class-0
baseline produces none, so its cell is a dash rather than a fabricated 0.5.

### 7.5 Selection used the training rows only

Selection ran on 5-fold `StratifiedKFold(shuffle=True, random_state=42)` over the 24,000
training rows. The held-out 6,000 were not read by `ml/train.py` at all —
`selection.test_rows_used_for_selection` is `0` in `models/metrics.json`.

| Rank | Candidate | mean CV F1 | mean CV recall | mean CV precision | mean CV ROC-AUC |
|---:|---|---:|---:|---:|---:|
| 1 | Decision Tree | **0.4643** | 0.3513 | 0.6868 | 0.7555 |
| 2 | Random Forest | 0.4191 | 0.3001 | 0.6959 | 0.7765 |
| 3 | Logistic Regression | 0.3647 | 0.2452 | 0.7118 | 0.7261 |

Objective, recorded verbatim in `models/metrics.json`: maximise mean cross-validated F1 on class
1, because 77.88 % of the sample is class 0 and accuracy is therefore dominated by the majority
class; ties within 0.005 absolute F1 break on recall, then precision. F1 is the right primary
here because it charges for both failure modes — a missed defaulter (FN) and a false alarm (FP) —
whereas recall alone would reward a model that flags everyone.

The choice is Decision Tree, and it is not the ROC-AUC winner: the Random Forest ranks best by
ROC-AUC (0.7765 vs 0.7555), a threshold-free ranking measure, yet is worse at the 0.5 operating
point on both F1 and recall — the two metrics the objective uses. Both facts are stated rather
than smoothed over, because the report must not imply the selected model dominates the
alternatives; it wins on the stated objective, not on every measure.

Cross-validation ordering also agrees with the held-out ordering, which is the useful sanity
check: the model chosen without seeing the test set is the one that wins on it.

### 7.6 Reproducibility

Two independent runs — separate output directories, nothing reused — were compared field by
field (`evidence/s4/determinism.txt`): `models/metrics.json` is **identical** across 208 numeric
fields, largest absolute difference **0.0**; the three candidate `joblib` artifacts, the shipped
`best_pipeline.joblib`, all four figures and `model_manifest.json` are **byte-identical**. The
only fields excluded from the comparison are the run timestamps, and the only normalisation is
the output-directory prefix in recorded paths.

`models/metrics.json` records the dataset SHA-256, the split and its seed, every
hyper-parameter, the CV numbers per fold, the per-model test metrics with their confusion
matrices, and the package versions (python 3.12.14, scikit-learn 1.9.1, numpy 2.5.4, pandas
3.1.0, joblib 1.6.0).

### 7.7 What this does not show

1. **No calibration.** The probabilities are uncalibrated; no calibration test has been run, and
   the report must not describe 0.72 as "a 72 % chance" in any validated sense.
2. **No threshold optimisation.** 0.5 was evaluated, not chosen. Every number above is at 0.5.
   A different threshold would need train/validation-only selection and its own evidence.
3. **No significance testing.** The 3.84-point accuracy edge over the baseline and the gaps
   between the three models are point estimates on one split; no confidence interval or
   significance test was run, so "better" here means "higher on these 6,000 rows".
4. **Numeric codes, not ordinal semantics.** `EDUCATION` and `MARRIAGE` are still fed in as
   integers (contract §3.2). A linear model can only fit a straight-line effect on a code that is
   not ordinal, which is one reason the Logistic Regression ranks last.
5. **Historical and foreign.** 2005 Taiwan, NTD, 30,000 accounts. Nothing here transfers to a
   current Malaysian portfolio without new evidence.

---

## 8. Evidence index

| Path | Produced by | Content |
|---|---|---|
| `evidence/s0/inspect_dataset.txt` | `ml/inspect_dataset.py` | 12 contract checks, dtypes, ranges, notation census, class counts |
| `evidence/s0/verify_draft_claims.txt` | `ml/verify_draft_claims.py` | 68 draft claims recomputed, 67 confirmed, 1 error; includes Table 9 arithmetic |
| `evidence/s0/draft_v1_extracted.txt` | stdlib OOXML extraction | v1 draft text |
| `evidence/s0/draft_v3_extracted.txt` | stdlib OOXML extraction | v3 draft text + tables |
| `evidence/s3/eda_run.txt` | `ml/generate_eda.py` | full stdout: class counts, descriptive statistics per feature, per-class `AGE`/`LIMIT_BAL`, category counts and rates, strongest correlations, written file sizes |
| `evidence/s3/eda_files.txt` | `ls -l`, `sha256sum` | the seven generated files with sizes and SHA-256; seed checksum unchanged |
| `evidence/s3/eda_determinism.txt` | two runs, `sha256sum`, `diff` | byte-for-byte identical regeneration |
| `evidence/s3/eda_render_after_restart.txt` | Pillow in a fresh container | all six PNGs decode from disk with their pixel dimensions |
| `evidence/s4/eda_source_line.txt` | `ml/generate_eda.py`, `git show 7ab66ce:`, `sha256sum` | F-1 fix: figure 06 gains its source line, and only figure 06 changes |
| `evidence/s4/train.txt` | `ml/train.py` | full stdout: dataset identity, split and its class counts, per-candidate CV table, selection |
| `evidence/s4/evaluate.txt` | `ml/evaluate.py` | full stdout: per-model accuracy/precision/recall/F1/AUC and TN/FP/FN/TP, baseline, artifact checksum, figures written |
| `evidence/s4/train_rerun.txt`, `evidence/s4/evaluate_rerun.txt` | second independent run into `models_rerun/` | the same two commands, same output |
| `evidence/s4/determinism.txt` | field-by-field comparison of the two runs | `metrics.json` identical across 208 numeric fields; all artifacts and figures byte-identical |
| `evidence/s4/contract_checks.txt` | `models/metrics.json` | the six contract checks: split, scaler-on-train leak test, arithmetic consistency, feature order, artifact identity, no test-set tuning |
| `evidence/s4/feature_importances.txt` | shipped `best_pipeline.joblib` | the selected tree's 23 importances; `PAY_0` 68.01 %, `PAY_2` 13.77 % |
| `evidence/s4/pytest.txt` | `pytest tests -q` | 64 tests, including the S4 model-contract tests |

Reproduce all of it:

```bash
python3 ml/inspect_dataset.py --csv data/UCI_Credit_Card.csv
python3 ml/verify_draft_claims.py --csv data/UCI_Credit_Card.csv
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl \
  -v "$PWD:/app:z" -w /app aihubcampus-web:local \
  python ml/generate_eda.py --csv data/UCI_Credit_Card.csv --out models/eda
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl \
  -v "$PWD:/app:z" -w /app aihubcampus-web:local \
  python -m ml.train --csv data/UCI_Credit_Card.csv --out models
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e MPLCONFIGDIR=/tmp/mpl \
  -v "$PWD:/app:z" -w /app aihubcampus-web:local \
  python -m ml.evaluate --models-dir models
```

The two S0 scripts are stdlib-only by design so they run before `requirements.txt` exists, and
both exit non-zero when the data disagrees with the documented contract. The S3 generator is
the first tool that needs the pinned ML environment (pandas + matplotlib); `ml/train.py` and
`ml/evaluate.py` add scikit-learn and joblib, and must run in the project image so the pinned
versions in `models/metrics.json` are the versions that actually produced the numbers.
