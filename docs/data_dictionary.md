# Data dictionary — UCI credit-card default dataset

Contract for `data/UCI_Credit_Card.csv` and for every dataset an admin later uploads.
The machine-readable source of this document is `ml/schema.py`; the validator that
enforces it is `src/validation.py`. If the two ever disagree, the code is authoritative
and this file is a bug.

- **Source:** UCI Machine Learning Repository, *Default of Credit Card Clients*
  (Yeh & Lien, 2009), as supplied for the assignment. Historical Taiwanese credit-card
  accounts, April–September 2005.
- **Seed file:** `data/UCI_Credit_Card.csv` — 30,000 rows, 25 columns, 2,862,995 bytes.
- **Seed SHA-256:** `a0f0ab49d6326671d6cd83be5c88dcf18007025fe9a53ecd699119c871176ca1`
- **Seed metadata checksum:** `ceae980f66ed32281e669b2d3dfd67c6e5cbba973f0c10637187d5f591bb8a27`
  (recorded value is the one printed by `python -m ml.inspect_dataset`; see
  `evidence/s2/inspect_dataset.txt`). Computed as SHA-256 over the canonical JSON of
  `{sha256, record_count, column_count, feature_count, class_zero, class_one, columns,
  features}` — see `ml.schema.metadata_checksum`.
- **The seed file is immutable.** It is never edited, rewritten or "cleaned" by any tool
  in this repository. Validation reads it and reports; it does not repair
  (`docs/source_of_truth.md`, precedence rule 5).

## Contract shape

- Exactly **25 columns**, in the order below. Order is part of the contract: a file with
  the right columns in the wrong order is rejected.
- `ID` is a technical row identifier. It is **excluded from training** and from the
  user form.
- `default.payment.next.month` is the **target**. It is excluded from the feature set and
  never appears on the inference form.
- The remaining **23 columns**, in this order, are the model and form contract
  (`ml.schema.FEATURES`).
- All numeric values are **whole numbers** (no decimals). Monetary amounts are in
  **NTD** (New Taiwan dollars), the unit of the source data. No currency conversion is
  applied anywhere.

## Columns

| # | Column | Kind | Unit | Month | Observed in seed | Validation | Notes |
|---:|---|---|---|---|---|---|---|
| 1 | `ID` | identifier | — | — | 1–30,000 | unique, ignored | Not a feature. Never shown, never trained on. |
| 2 | `LIMIT_BAL` | amount | NTD | — | 10,000–1,000,000 | `>= 1`; form band 10,000–1,000,000 | Credit limit including supplementary cards. |
| 3 | `SEX` | code | code | — | 1, 2 | `{1, 2}` | 1 = male, 2 = female (dataset coding). Never used to drive a recommendation. |
| 4 | `EDUCATION` | code | code | — | 0–6 | `{0,1,2,3,4,5,6}` | 1 graduate school, 2 university, 3 high school, 4 others, 0/5/6 undocumented. Kept as legal codes; never silently remapped. |
| 5 | `MARRIAGE` | code | code | — | 0–3 | `{0,1,2,3}` | 1 married, 2 single, 3 others, 0 unknown/other. Handled explicitly. |
| 6 | `AGE` | amount | years | — | 21–79 | `18 <= AGE <= 100` | Observed range is not used as the form bound; 18–100 is the documented choice. |
| 7 | `PAY_0` | status code | code | Sep 2005 | −2–8 | `{-2..9}` | Repayment status, most recent month. See code table below. |
| 8 | `PAY_2` | status code | code | Aug 2005 | −2–8 | `{-2..9}` | There is **no `PAY_1`** in the source; it must not be invented. |
| 9 | `PAY_3` | status code | code | Jul 2005 | −2–8 | `{-2..9}` | |
| 10 | `PAY_4` | status code | code | Jun 2005 | −2–8 | `{-2..9}` | |
| 11 | `PAY_5` | status code | code | May 2005 | −2–8 | `{-2..9}` | |
| 12 | `PAY_6` | status code | code | Apr 2005 | −2–8 | `{-2..9}` | |
| 13 | `BILL_AMT1` | signed amount | NTD | Sep 2005 | −165,580–964,511 | finite whole number; **negative allowed** | Statement balance. A negative balance is a credit, not an error. |
| 14 | `BILL_AMT2` | signed amount | NTD | Aug 2005 | −69,777–983,931 | finite whole number; negative allowed | |
| 15 | `BILL_AMT3` | signed amount | NTD | Jul 2005 | −157,264–1,664,089 | finite whole number; negative allowed | |
| 16 | `BILL_AMT4` | signed amount | NTD | Jun 2005 | −170,000–891,586 | finite whole number; negative allowed | |
| 17 | `BILL_AMT5` | signed amount | NTD | May 2005 | −81,334–927,171 | finite whole number; negative allowed | |
| 18 | `BILL_AMT6` | signed amount | NTD | Apr 2005 | −339,603–961,664 | finite whole number; negative allowed | |
| 19 | `PAY_AMT1` | non-negative amount | NTD | Sep 2005 | 0–873,552 | `>= 0` | Amount actually paid that month. |
| 20 | `PAY_AMT2` | non-negative amount | NTD | Aug 2005 | 0–1,684,259 | `>= 0` | |
| 21 | `PAY_AMT3` | non-negative amount | NTD | Jul 2005 | 0–896,040 | `>= 0` | |
| 22 | `PAY_AMT4` | non-negative amount | NTD | Jun 2005 | 0–621,000 | `>= 0` | |
| 23 | `PAY_AMT5` | non-negative amount | NTD | May 2005 | 0–426,529 | `>= 0` | |
| 24 | `PAY_AMT6` | non-negative amount | NTD | Apr 2005 | 0–528,666 | `>= 0` | |
| 25 | `default.payment.next.month` | target | label | next month | 0: 23,364 · 1: 6,636 | `{0, 1}` | 1 = defaulted on the next month's payment, 0 = did not. |

"Observed in seed" is descriptive: it is what `ml/inspect_dataset.py` measured in the
supplied file, not a validation bound. Only the "Validation" column is enforced.

## Month mapping

The source is a six-month window. The most recent month is September 2005 and the
columns run backwards to April 2005:

| Historical slot | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|
| Month | Sep 2005 | Aug 2005 | Jul 2005 | Jun 2005 | May 2005 | Apr 2005 |
| Repayment status | `PAY_0` | `PAY_2` | `PAY_3` | `PAY_4` | `PAY_5` | `PAY_6` |
| Statement balance | `BILL_AMT1` | `BILL_AMT2` | `BILL_AMT3` | `BILL_AMT4` | `BILL_AMT5` | `BILL_AMT6` |
| Amount paid | `PAY_AMT1` | `PAY_AMT2` | `PAY_AMT3` | `PAY_AMT4` | `PAY_AMT5` | `PAY_AMT6` |

The `PAY_` status series is numbered `0, 2, 3, 4, 5, 6` in the source. `PAY_1` does not
exist — the numbering gap is a property of the published dataset, not a missing column.

## Repayment-status codes (`PAY_0`, `PAY_2` … `PAY_6`)

| Code | Meaning |
|---:|---|
| −2 | no consumption that month |
| −1 | paid in full that month |
| 0 | revolving credit / minimum payment |
| 1–8 | one to eight months of payment delay |
| 9 | nine months or more of delay (legal per the source scale; not present in this sample) |

Negative codes are meaningful and are preserved. They are never clipped, floored to
zero or treated as missing.

## Target semantics

`default.payment.next.month` is the label for the month **after** the September 2005
observation window: `1` means the account defaulted on the next month's payment, `0`
means it did not. The positive class is 22.12% of the seed (6,636 / 30,000) — an
imbalanced problem, which Sprint 4 addresses explicitly rather than by resampling the
seed in place.

## What the validator rejects

`src/validation.py` returns every problem it finds, each with a stable code and a
message that names the column and the number of offending rows — never a cell value,
row content or uploaded filename. Structural problems stop the check (a file with a
broken header cannot be value-checked); value problems are all collected.

| Code | Reason |
|---|---|
| `empty_file` | zero bytes uploaded |
| `file_too_large` | larger than 10 MB (10,485,760 bytes) |
| `not_utf8` | not valid UTF-8 text |
| `malformed_csv` | unparsable CSV (e.g. a row with the wrong field count) |
| `duplicate_column` | a header name appears more than once |
| `missing_column` | one or more of the 25 required columns is absent |
| `extra_column` | a column outside the 25-column contract is present |
| `column_order` | all 25 present but not in the documented order |
| `empty_data` | header present, no data rows |
| `missing_value` | empty or NaN cell |
| `not_numeric` | non-numeric text in a numeric column |
| `non_finite` | `inf` / `-inf` |
| `non_integer` | fractional value in a whole-number column |
| `unsupported_code` | code outside the documented set for `SEX` / `EDUCATION` / `MARRIAGE` / `PAY_*` |
| `invalid_target_value` | target value other than 0 or 1 |
| `out_of_range` | below a documented minimum (`PAY_AMT* >= 0`, `LIMIT_BAL >= 1`, `18 <= AGE <= 100`) or above a documented maximum |

Rejection is non-destructive: the file is quarantined under a generated name and left
untouched for diagnosis. Nothing is dropped, filled, clipped or coerced.

## Upload quarantine

An admin upload is written to `data/quarantine/` (git-ignored) **before** it is parsed:

- The stored name is generated — `YYYYmmddTHHMMSSZ-<12 hex>.csv` — so the uploaded name
  can never influence a path. Path traversal is structurally impossible.
- The uploaded name survives only as a display label (`original_filename_safe`): final
  path component, no control characters or separators, forced `.csv` suffix, 120 chars.
- Files are created exclusively (`O_CREAT|O_EXCL|O_NOFOLLOW`, mode `0600`), so an
  existing file or a planted symlink is never overwritten or followed.
- The SHA-256 of the bytes is recorded with the file; the dataset version identity is
  the metadata checksum described at the top of this document.
- The seed `data/UCI_Credit_Card.csv` is never a destination. An activated upload
  becomes a separate dataset version and cannot replace the benchmark evidence.

## Reproducing the facts in this document

```sh
python -m ml.inspect_dataset --csv data/UCI_Credit_Card.csv
python -m pytest tests/test_schema.py -q
```
