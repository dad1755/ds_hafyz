# 7. Dataset Description

Draft, Sprint 14. All facts in this section were produced by `ml/inspect_dataset.py` and are
recorded in `evidence/s0/inspect_dataset.txt`; the column contract is `docs/data_dictionary.md`,
whose machine-readable source is `ml/schema.py`.

## 7.1 Source and citation

The dataset is **Default of Credit Card Clients**, UCI Machine Learning Repository dataset 350
(Yeh, 2009; DOI 10.24432/C55S3H), introduced in Yeh & Lien (2009). It describes credit-card
clients of a Taiwanese bank over the billing months April to September 2005. Monetary amounts are
in New Taiwan Dollars (NTD); no conversion is applied anywhere in the project. The local copy is
`data/UCI_Credit_Card.csv`, 2,862,995 bytes, SHA-256
`a0f0ab49d6326671d6cd83be5c88dcf18007025fe9a53ecd699119c871176ca1`. The file is used unmodified:
no record is edited, no value imputed, no row deleted.

## 7.2 Shape and class distribution

| Fact | Value |
|---|---|
| Rows | 30,000 |
| Columns | 25 |
| Predictors used by the model | 23 (`ID` and the target are excluded) |
| Missing cells | 0 |
| Duplicate full rows | 0 |
| Class 0 — no default next month | 23,364 (77.88%) |
| Class 1 — default next month | 6,636 (22.12%) |
| Target | `default.payment.next.month`, values `{0, 1}` |

The 78:22 split is the single most consequential property of the data. It is why accuracy is not
used to select a model (§13) and why recall is reported next to every accuracy figure.

## 7.3 The 23 features

| Group | Count | Columns |
|---|---:|---|
| Credit profile | 5 | `LIMIT_BAL`, `SEX`, `EDUCATION`, `MARRIAGE`, `AGE` |
| Repayment status, six months | 6 | `PAY_0` (Sep 2005), `PAY_2` (Aug), `PAY_3` (Jul), `PAY_4` (Jun), `PAY_5` (May), `PAY_6` (Apr) |
| Statement balances | 6 | `BILL_AMT1` … `BILL_AMT6` |
| Amounts paid | 6 | `PAY_AMT1` … `PAY_AMT6` |

There is **no `PAY_1` column** in the source. The dataset's six repayment-status columns are
`PAY_0, PAY_2, PAY_3, PAY_4, PAY_5, PAY_6`, and the project never invents a `PAY_1`; the earlier
draft's implied `PAY_1` was a naming error, corrected here (§19.2, E4).

`ID` is a sequential row index, not a customer identifier: the dataset is pseudonymous. It is
excluded from training and from the form.

## 7.4 Data types and the notation wrinkle

All 23 features are numeric. The monetary columns are whole NTD amounts, but the CSV export mixes
plain integers and scientific notation (`5e+05` and similar): 4,262 cells are in scientific
notation — `LIMIT_BAL` 4,150; `PAY_AMT1–6` 16, 18, 9, 11, 19, 12; `BILL_AMT1–6` 2, 3, 4, 5, 8, 5.
Every one of them parses to a whole NTD value with no fractional part. The validator therefore
parses numerically and asserts whole values, and the report does not claim a clean all-integer
dtype table (correction E1 in `docs/report_evidence.md` §4).

Negative values are legitimate in `BILL_AMT1–6` (a negative balance is a credit, not an error);
`PAY_AMT1–6` are non-negative; `PAY_*` status codes run from −2 to 9.

## 7.5 Relevance, and its limits

The dataset is suitable because it is real, public, well documented, structured and binary — the
exact shape the brief asks for — and because it carries a genuine class imbalance that makes the
evaluation question interesting rather than trivial. It is limited because it is historical
(2005), foreign (Taiwan), small (30,000 rows, 23 predictors) and pseudonymous, with no
information about the bank's own policies. Those limits are discussed in §22, not hidden here.

## Evidence

- `evidence/s0/inspect_dataset.txt`
- `docs/data_dictionary.md`
- `ml/schema.py`
- `evidence/s2/inspect_dataset.txt`
- `docs/report_evidence.md`
- `README.md`
