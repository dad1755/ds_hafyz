# Report evidence — what is verified, what is claimed

Maintained from Sprint 0 onward. `Group Project 40%.md` is the assessment authority and
`blueprint.md` the implementation spec; this file records which statements in the report
are backed by executed commands and which are still assertions from a draft.

Rule: a number appears in the report as a **result** only when a command in this
repository produced it and the output is archived under `evidence/`. Everything else is
labelled `claimed`.

Scope at Sprint 14: §1–§7 record the S0–S4 evidence as it was gathered; §8–§16 add the S5–S13
record (artifact and inference, storage and authentication, the two user-facing modules, the
dataset manager, the evaluation panels, testing, hardening, deployment); §17 gives the final
disposition of every claim in the earlier draft; §18 indexes the files. The report drafts in
`docs/report/` cite this file rather than restating it.

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

## 3. Claimed but NOT verified (as of S0; every row is now settled — see the last column)

This table is kept as the historical record of what was unproven when the project started. Each row
now names the section that settles it, so a reader can see both the gap and its closure.

| Claim | Source | Why it was unverified | Settled by |
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

## 8. Sprint 5 — model artifact, inference service and risk bands

**Claim → evidence.** The selected pipeline is the file that was evaluated, not a retrained lookalike.

| Claim | Evidence | Status |
|---|---|---|
| The shipped artifact is the selected candidate | `models/metrics.json` `checks.artifact`: `predictions_identical_to_candidate: true`, `probabilities_identical_to_candidate: true`, `source_candidate: decision_tree`, same SHA-256 for both | verified |
| Artifact identity | 8,187 bytes, SHA-256 `48ce02563b2aad9fbf9397603c642b0319be617c57fde8e1fd26ec08d518ad7b`, version `aihubcampus-default-risk-1+48ce02563b2a` | verified (`evidence/s5/verify_artifact.txt`) |
| Eleven ordered checks run before load | `evidence/s5/verify_artifact.txt` — files, manifest schema, checksum, provenance, dataset identity, feature contract, class semantics, pickle allowlist, pipeline schema, deterministic self-check, metrics consistency | verified |
| A tampered or foreign artifact is refused | `evidence/s5/tamper.txt` — mutated bytes fail the checksum check; a pickle referencing a non-allowlisted class is refused before deserialisation | verified |
| The screen is not a second implementation | `evidence/s5/cli_vs_pipeline.txt` — CLI path and loaded pipeline agree on class, probability and band | verified |
| Band boundaries are exact and monotone | `evidence/s5/boundaries.txt` — 9 edge values (`0.0, 0.2499, 0.25, 0.4999, 0.50, 0.7499, 0.75, 0.9999, 1.0`) map `low, low, watch, watch, high, high, critical, critical, critical`; a 10,001-point sweep never skips or reverses a band (`tests/test_prediction.py`) | verified |

**What this does not show.** The eleven checks establish provenance and structural integrity, not
statistical validity: they cannot prove the artifact is a good model, only that it is this
project's model. Calibration is not measured anywhere in the project.

---

## 9. Sprint 6 — SQLite, authentication, sessions and role guards

| Claim | Evidence | Status |
|---|---|---|
| Eight tables with the documented constraints | `src/db.py`: `users` (unique index on `lower(username)`), `sessions`, `login_attempts`, `prediction_logs`, `dataset_versions` (partial unique index `dataset_versions_one_active … WHERE is_active = 1`), `dataset_rejections`, `audit_events`, `schema_migrations`; idempotent migrations | verified |
| Passwords are Argon2id, never SHA-256 | `src/security.py`: `$argon2id$v=19$m=65536,t=3,p=4$…`, constant-time verify, no SHA-256 password path; `evidence/s6/security_smoke.txt` | verified |
| Password policy is enforced on every new password | `src/security.py`: 12-character minimum plus a denylist; the seeded operator password is 7 characters, so the account carries `must_change_password = 1` (deviation D13) | verified (`evidence/s6/init_admin.txt`) |
| Throttling is 5 failures / 15 minutes / 15-minute lock | `src/security.py` `THROTTLE_MAX_FAILURES = 5`, `THROTTLE_WINDOW = 15 min`, `THROTTLE_LOCKOUT = 15 min`; T02 in `docs/test_matrix.md` | verified |
| Sessions are server-side, hashed and expiring | `src/security.py`: `sessions.token_hash` is the SHA-256 of the bearer token, `SESSION_TTL = 8 h`, revocation timestamp honoured | verified (`evidence/s6/schema_and_storage.txt`) |
| Privileged functions re-check the role themselves | `src/security.py` `require_role`; every function in `src/accounts.py` and `src/data_manager.py` calls it first; 14-function sweep in T03 | verified |
| Accounts and rows survive a restart | `evidence/s6/restart_persistence.txt` — same row counts and a working sign-in after a container restart | verified |

**What this does not show.** No penetration test, no audit of the session model against OWASP's full
checklist, and the XSRF cookie is issued without `Secure` because TLS terminates at the edge
(finding F-2, unfixed, `docs/deployment.md` §10.5).

---

## 10. Sprint 7 — user prediction UI

| Claim | Evidence | Status |
|---|---|---|
| The form is the 23-feature contract | `src/pages_prediction.py` asserts at import that the four input groups cover `ml.schema.FEATURES` exactly once in order | verified (`evidence/s7/pytest_s7.txt`) |
| Screen output equals pipeline output | `evidence/s7/ui_vs_pipeline.txt` — class, probability (compared with `repr()`, not a tolerance) and band identical over six synthetic rows | verified |
| Validation precedes inference | T08: clearing `LIMIT_BAL` yields one error naming the field, no result panel, 0 rows written | verified |
| Result panel content | class, probability to two decimals labelled *estimated, uncalibrated*, band, advice, threshold 0.50, model version, three disclosures; demonstrator row `0.7195348837209302` → `0.72`, band `High` | verified (`evidence/s7/result_375px.png`, `evidence/s11/test-results/demo_prediction.txt`) |
| No horizontal overflow at 375 px or desktop | `evidence/s7/browser_check.txt` — 0 overflow at 375×812 and 1280×800 | verified |
| The demonstrator is labelled synthetic | `src/pages_prediction.py`: the button text and its caption say the values are invented, not a dataset row | verified |
| Repeats do not duplicate rows | `src/predictions.py`: per-session fingerprint map returns the existing row with `created=False` | verified |
| History is scoped to the session user | `src/predictions.py` filters by the user id resolved from the token inside the query; the function takes no user argument | verified (T03 sweep includes it) |

**What this does not show.** Usability was not measured with users; accessibility was checked for
layout overflow only, not with a screen reader.

---

## 11. Sprint 8 — administrator user management

| Claim | Evidence | Status |
|---|---|---|
| List, create, edit display name, change role, reset password, deactivate/reactivate | `src/accounts.py`; `evidence/s8/ui_query.txt`; screenshots `evidence/s8/admin_375px.png`, `created_375px.png` | verified |
| No delete path exists | no `delete_user` and no `DELETE FROM users` in `src/`; deactivation revokes open sessions in the same transaction | verified |
| Every write is audited with a named action | `evidence/s8/audit_probe.txt` records `user.created`, `user.display_name_changed`, `user.role_changed`, `password.reset`, `user.deactivated`, `user.activated`, with non-sensitive detail only | verified |
| A user cannot reach the functions behind the page | T03: 14-function sweep raises `PermissionDenied` and writes one `auth.denied` row per attempt; guard test asserts the list is ≥ 14 entries | verified |
| The last enabled administrator cannot be removed | enforced inside the write transaction; asserted by the S8 gate (`docs/acceptance/S08.md`) | verified |

---

## 12. Sprint 9 — dataset manager

| Claim | Evidence | Status |
|---|---|---|
| Staged ≠ deployed is unmistakable | `evidence/s9/probe_datasets.txt`, `evidence/s9/dataset_375px_initial.png`, `dataset_375px_staged.png`; after activation the page states the active dataset did not build the deployed model | verified |
| Uploads are quarantined under a generated name | `src/data_manager.py`; `evidence/s9/probe_datasets.txt` shows `quarantined_filename: 20261026T180209Z-….csv`, not the uploaded name | verified |
| Malformed uploads are refused with a code and a reason | `dataset_rejections` rows `missing_column` and `invalid_target_value`, each with a persisted reason and a `dataset.rejected` audit row | verified (T06) |
| 10 MiB cap, boundary exact | `src/validation.py` `MAX_UPLOAD_BYTES = 10 * 1024 * 1024`; adversarial tests accept 10 MiB and refuse 10 MiB + 1 byte | verified |
| Exactly one dataset version can be active | partial unique index in `src/db.py`; a test bypasses the code with a direct `UPDATE` and the index refuses it | verified |
| Nothing is trained or replaced on upload | audit detail `retraining_triggered: false`, `model_replaced: false` on every staged/activated/rejected row (`evidence/s9/probe_datasets.txt`); `evidence/s9/hygiene.txt` shows `src/data_manager.py` calls no `.fit(`, `.predict(`, `.dump(`, `.load(` or `.to_pickle(` | verified |
| Only aggregates are shown | the preview object has no `records` attribute; one row per column with min/max/mean/distinct | verified (T05) |

---

## 13. Sprint 10 — model evaluation panels

| Claim | Evidence | Status |
|---|---|---|
| The page shows the recorded numbers, not copies | `evidence/s10/trace_metrics.txt` — two renderings diffed against `models/metrics.json`: 39 lines and 15 lines identical, `RESULT: PASS … 0 mismatches` | verified |
| The page cannot show a stale hard-coded value | a test rewrites a copy of `metrics.json` with sentinel values and asserts the page renders them (`evidence/s10/pytest_s10.txt`) | verified |
| No v3 draft statistic is hard-coded in the app | `evidence/s10/draft_grep.txt` — the grep for draft figures in `app.py` and `src/` returns nothing | verified |
| The panel survives a restart and re-renders from disk | `evidence/s10/restart.txt` | verified |
| The user's navigation contains no admin section | `evidence/s10/evaluation_user_nav.png`; T01 records both navigation strings exactly | verified |
| Charts are colour-blind-safe and labelled | `src/charts.py`: Okabe–Ito palette, one hatch per model and per correct/error cell, every mark labelled | verified (`evidence/s10/browser_check.txt`) |

---

## 14. Sprint 11 — automated testing and adversarial verification

| Claim | Evidence | Status |
|---|---|---|
| 285 test cases pass | `evidence/s11/test-results/pytest_all_verbose.txt`: `285 passed in 598.66s`, 0 failed, 0 error, 0 skipped | verified |
| T01–T12 map to real node ids | `docs/test_matrix.md`; `evidence/s11/test-results/t_matrix_extract.txt` checks every cited id appears in the transcript as PASSED | verified |
| The sweep cannot pass vacuously | `tests/test_adversarial.py` asserts `len(PRIVILEGED_CALLS) >= 14` and names two required entries | verified |
| Six sensitive paths are not served | `evidence/s11/probe_http.txt`: `/storage/aihubcampus.db`, `/app/storage/aihubcampus.db`, `-wal`, `/data/UCI_Credit_Card.csv`, `/models/best_pipeline.joblib`, `/.env` all return the 4,096-byte app shell | verified |
| Upload limits, quarantine containment, secret scan, log scan, XSRF/CORS | `tests/test_adversarial.py`; `evidence/s11/probe_logs.txt` (no secret in container logs); `evidence/s11/test-results/check_no_secrets.txt` | verified |
| Sources compile and the suite survives a restart | `evidence/s11/test-results/compileall.txt`; `evidence/s11/restart.txt` | verified |
| Gaps | no load/soak test, no cross-browser matrix, no screen-reader audit, no penetration test | stated, not tested |

---

## 15. Sprint 12 — production-like hardening and recovery

| Claim | Evidence | Status |
|---|---|---|
| The runtime is digest-pinned and immutable | `Dockerfile`: `python:3.12-slim@sha256:…`; `compose.yaml`: `read_only: true`, `cap_drop: [ALL]`, `security_opt: no-new-privileges`, tmpfs `/tmp`, one writable volume | verified (`evidence/s12/smoke_test.txt`) |
| The release gate passes | `evidence/s12/release_gate.txt`: `RESULT: 27 passed, 0 failed`, `VERDICT: PASS (mechanical checks)` at `f70ab3b` | verified |
| Backup and restore actually round-trip | `evidence/s12/backup.txt`, `evidence/s12/roundtrip.txt` — restore into a fresh volume reproduces the row counts and the live database SHA-256 is unchanged by the drill | verified |
| A fresh clone can build and verify | `evidence/s12/fresh_clone.txt` | verified |
| No operator secret is in any tracked file | `evidence/s12/secrets.txt`: 290 files scanned, 4 secret values loaded, `PASS` | verified |
| The suite still passes on the pinned base | `evidence/s12/release_gate.txt` — 285 passed in 572.74 s | verified |

**A real defect this sprint fixed, not merely described.** The first backup implementation staged
its snapshot in `/tmp`, which hardening had made a tmpfs, so `docker cp` could not read it. The
independent S12 gate failed the sprint on it (`docs/acceptance/S12.md`); `scripts/backup.sh` now
streams the snapshot out with `docker exec … cat` and compares checksums.

---

## 16. Sprint 13 — live deployment through the Cloudflare tunnel

| Claim | Evidence | Status |
|---|---|---|
| The app is served over HTTPS at the public hostname | `evidence/s13/browser_check.txt`: 29 PASS lines, `server: cloudflare`; sign-in, admin home, prediction, dataset staging and forced password change all rendered through the tunnel | verified |
| No origin port is published | `evidence/s13/smoke_test.txt`: `PortBindings={}` on both containers; `ports:` absent from `compose.yaml` | verified |
| The public smoke test passes | `evidence/s13/smoke_test.txt`: `16 passed, 0 failed, 0 skipped` | verified |
| The release gate passes at the deployed commit | `evidence/s13/release_gate.txt`: `25 passed, 0 failed` at `b3d0144`; the independent gate's verdict is PASS at `49540a6` (`docs/acceptance/S13.md`) | verified |
| No operator secret in 312 tracked files | `evidence/s13/check_no_secrets.txt` | verified |
| Three findings are real and unfixed | F-1 hard refresh signs the user out (session token lives only in `session_state`), F-2 the XSRF cookie has no `Secure`, F-3 `http://` answers 200 instead of redirecting — `docs/deployment.md` §10.5, reproduced in `docs/acceptance/S13.md` | verified as defects |

---

## 17. The v3 draft — final status of every claim

The draft this project replaces (`Credit_Card_Default_Prediction_Project-v3.docx`) is treated as a
set of claims to test. Each row below is its final disposition; the report text follows this table,
not the draft.

| # | Draft claim | Final status | Evidence |
|---:|---|---|---|
| 1 | Dataset is 30,000 × 25, 23 predictors | **confirmed** | `evidence/s0/inspect_dataset.txt` |
| 2 | Class shares 77.88% / 22.12% | **confirmed** | `models/eda/summary.json` |
| 3 | Table 8 descriptive statistics (`LIMIT_BAL`, `AGE`, `BILL_AMT1–2`, `PAY_AMT1–2`) | **confirmed** — 68 claims recomputed, 67 confirmed to the draft's rounding, 1 error | `evidence/s0/verify_draft_claims.txt` |
| 4 | Table 9 model metrics (LR 0.8077, DT 0.8172, RF 0.8122 accuracy; DT F1 0.4620) | **confirmed** to four decimals from the shipped artifact | `docs/report_evidence.md` §7.3 |
| 5 | Feature importance `PAY_0` 68.01%, `PAY_2` 13.77% | **confirmed** exactly | `evidence/s4/feature_importances.txt` |
| 6 | Six EDA charts exist | **superseded** — six charts were regenerated from the CSV; the draft's embedded images are not reused | `models/eda/`, `evidence/s3/eda_files.txt` |
| 7 | Passwords hashed with SHA-256 | **corrected** — Argon2id (`m=65536,t=3,p=4`); no SHA-256 password path exists | `src/security.py`, `evidence/s6/security_smoke.txt` |
| 8 | Cloud hosting is future work | **corrected** — deployed and verified at `https://www.aihubcampus.online` | `evidence/s13/browser_check.txt` |
| 9 | Class 0 labelled "On Time" | **corrected** — "Predicted non-default next month" (a prediction, not a fact) | `docs/inference_contract.md`, §16.3 of the report |
| 10 | Education "others" default rate 5.7% | **corrected** — 5.69% is code 4 alone (n = 123); codes 0/4/5/6 together are 7.05% (n = 468) | `evidence/s3/eda_run.txt` |
| 11 | "Four main education groups" | **corrected** — seven observed codes (0–6), two undocumented by UCI | `models/eda/summary.json` |
| 12 | Implied `PAY_1` column | **corrected** — no `PAY_1` exists; the columns are `PAY_0, PAY_2…PAY_6` | `evidence/s0/inspect_dataset.txt` |
| 13 | "All 12 system tests pass", no output attached | **superseded** — T01–T12 mapped to node ids inside a 285-case transcript | `docs/test_matrix.md`, `evidence/s11/test-results/pytest_all_verbose.txt` |
| 14 | Admin and user modules function | **confirmed** as built (S6–S9), with the modules' limits stated | `evidence/s8/`, `evidence/s9/` |
| 15 | A fourteen-day schedule was met | **unconfirmed** — no record in this repository; the deadline is not recorded either. Not asserted as fact | `docs/rubric_matrix.md` §6 |
| 16 | Four-member division of work | **unconfirmed** — only the group can confirm it. The report carries placeholders, not invented names | `docs/rubric_matrix.md` §6, report §1 |
| 17 | LIMIT_BAL mean / std / median / quartiles | **confirmed** to the draft's rounding | `evidence/s0/verify_draft_claims.txt` |

Rows 15 and 16 are the two the report must not "fix" by writing something plausible. They are
marked unconfirmed in the report and in the rubric matrix, and the group can supply them at any time.

---

## 18. Evidence index

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
| `evidence/s5/verify_artifact.txt` | `python -m ml.verify_artifact` | the eleven artifact checks, each named, with their verdicts |
| `evidence/s5/tamper.txt` | `evidence/s5/tamper_demo.py` | a mutated artifact and a foreign pickle both refused |
| `evidence/s5/cli_vs_pipeline.txt` | `evidence/s5/compare_cli_vs_pipeline.py` | CLI, loaded pipeline and service agree on class, probability, band |
| `evidence/s5/boundaries.txt` | `evidence/s5/boundary_demo.py` | the nine band edges and the 10,001-point sweep |
| `evidence/s6/security_smoke.txt` | `evidence/s6/security_smoke.py` | hashing, policy, throttling, session revocation, RBAC refusals |
| `evidence/s6/schema_and_storage.txt` | `evidence/s6/inspect_db.py` | the eight tables, their indexes and constraints |
| `evidence/s6/restart_persistence.txt` | restart probe | accounts and rows survive a restart |
| `evidence/s7/ui_vs_pipeline.txt` | `evidence/s7/ui_vs_pipeline.py` | screen output equals pipeline output over six rows |
| `evidence/s7/browser_check.txt` | `evidence/s7/ui_screenshots.js` | render, overflow and screenshot checks at 375 px and desktop |
| `evidence/s8/audit_probe.txt` | `evidence/s8/audit_probe.py` | the audit rows each admin action writes |
| `evidence/s8/ui_query.txt` | `evidence/s8/ui_query.py` | what the admin page renders, read back from the page |
| `evidence/s9/probe_datasets.txt` | `evidence/s9/probe_datasets.py` | staging counts, both rejections, activation across a restart, audit detail |
| `evidence/s9/hygiene.txt` | `evidence/s9/hygiene.sh` | the dataset manager imports no training or serialisation path |
| `evidence/s10/trace_metrics.txt` | `evidence/s10/trace_metrics.py` | every value on the evaluation page diffed against `models/metrics.json`: 0 mismatches |
| `evidence/s10/draft_grep.txt` | `evidence/s10/draft_grep.sh` | no v3 draft statistic hard-coded in the app |
| `evidence/s11/test-results/pytest_all_verbose.txt` | `pytest tests -v` | 285 passed, 0 failed, in 598.66 s — the verbatim transcript |
| `evidence/s11/test-results/t_matrix_extract.txt` | `evidence/s11/extract_matrix.py` | every test id cited by `docs/test_matrix.md` appears in the transcript as PASSED |
| `evidence/s11/probe_http.txt` | `evidence/s11/probe_http.py` | six sensitive paths not served; XSRF/CORS and WebSocket behaviour |
| `evidence/s11/probe_logs.txt` | `evidence/s11/probe_logs.py` | no secret or hash in the container log |
| `evidence/s12/release_gate.txt` | `scripts/verify_release.sh --build --with-tests` | 27 checks passed, 0 failed; 285 tests on the pinned base |
| `evidence/s12/backup.txt`, `evidence/s12/roundtrip.txt` | `scripts/backup.sh`, `scripts/restore.sh` | snapshot streamed out, restored into a fresh volume, live database unchanged |
| `evidence/s12/secrets.txt` | `scripts/check_no_secrets.py` | 290 files scanned, zero operator secrets |
| `evidence/s13/browser_check.txt` | `evidence/s13/ui_tunnel.js` | 29 checks through the public hostname, all PASS |
| `evidence/s13/smoke_test.txt` | `scripts/smoke_test.sh --url …` | 16 passed, 0 failed; `PortBindings={}` |
| `evidence/s13/release_gate.txt` | `scripts/verify_release.sh` | 25 checks passed, 0 failed at the deployed commit |
| `evidence/s13/check_no_secrets.txt` | `scripts/check_no_secrets.py` | 312 files scanned, zero operator secrets |

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
