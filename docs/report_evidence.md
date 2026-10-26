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
| LR / DT / RF accuracy, precision, recall, F1 (Table 9) | v3 §4.2–4.3 | No artifact, seed or run log in repo; arithmetic alone is not evidence | S4 |
| Decision Tree is the best model | v3 §4.3, v1 §5 | Depends on reproduced metrics | S4 |
| Feature importance PAY_0 68.01%, PAY_2 13.77% | v3 Table 10 | No trained model to inspect | S4 |
| All 12 system tests pass (T01–T12) | v3 §6.1, v1 §6 | No test files, no recorded output | S11 |
| "Fourteen day" schedule met | v3 §1.4, v1 §7 | Planning assumption; deadline not confirmed by the lecturer | S14/S15 |
| Four-member division of work | v3 §1.4 | Not confirmed by the group | S15 (B8) |
| Passwords hashed with SHA-256 | v3 §5.2 | Not implemented; and the blueprint prohibits bare SHA-256 | S6 |
| Six EDA charts exist | v3 §3 | Draft embeds images; no script can regenerate them yet | S3 |
| Live Cloudflare deployment | operator authorisation | Authorised but not yet built or verified | S13 |
| Admin/user modules function | v3 §5.2, §6.1 | No code | S6–S8 |

---

## 4. Discrepancies found in Sprint 0 (report text must be corrected)

| # | Finding | Evidence | Required correction |
|---:|---|---|---|
| E1 | **4,262 monetary cells are in scientific notation** (`5e+05`, etc.): `LIMIT_BAL` 4,150; `PAY_AMT1–6` 16/18/9/11/19/12; `BILL_AMT1–6` 2/3/4/5/8/5. All parse to whole NTD (0 fractional values). | `evidence/s0/inspect_dataset.txt` | Report must not claim a clean all-integer dtype table. State that the export mixes plain and scientific notation and that validation parses numerically, asserting whole-NTD values. |
| E2 | **`EDUCATION` "others" default rate is 5.7% in the draft but that figure is code 4 alone**; the aggregate of codes 0,4,5,6 is **7.05%**. | `evidence/s0/verify_draft_claims.txt`, `MISMATCHES` section | Rewrite v3 §3.5: either report code 4 as 5.69% (n=123) or the true aggregate 7.05% (n=468). |
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

## 6. Evidence index

| Path | Produced by | Content |
|---|---|---|
| `evidence/s0/inspect_dataset.txt` | `ml/inspect_dataset.py` | 12 contract checks, dtypes, ranges, notation census, class counts |
| `evidence/s0/verify_draft_claims.txt` | `ml/verify_draft_claims.py` | 68 draft claims recomputed, 67 confirmed, 1 error; includes Table 9 arithmetic |
| `evidence/s0/draft_v1_extracted.txt` | stdlib OOXML extraction | v1 draft text |
| `evidence/s0/draft_v3_extracted.txt` | stdlib OOXML extraction | v3 draft text + tables |

Reproduce all of it:

```bash
python3 ml/inspect_dataset.py --csv data/UCI_Credit_Card.csv
python3 ml/verify_draft_claims.py --csv data/UCI_Credit_Card.csv
```

Both scripts are stdlib-only by design so they run before `requirements.txt` exists, and
both exit non-zero when the data disagrees with the documented contract.
