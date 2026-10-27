# 8. Data Preprocessing

Draft, Sprint 14. The contract this section describes is `docs/preprocessing_contract.md`, fixed
before any model was fitted; the implementation is `ml/train.py` and `src/validation.py`.

## 8.1 What the data needed, and what it did not

| Step | Decision | Justification |
|---|---|---|
| Missing values | None imputed | 30,000 rows × 25 columns contain **0** missing cells (`evidence/s0/inspect_dataset.txt`). Imputing would have invented values. |
| Duplicate rows | None removed | 0 duplicate full rows. |
| Irrelevant attributes | `ID` dropped, target separated | `ID` is a sequential index with no predictive meaning; keeping it would leak row order. |
| Data types | Parsed numerically, whole NTD asserted | 4,262 cells arrive in scientific notation; all parse to whole NTD values (§7.4). |
| Categorical encoding | **Not** one-hot encoded in the baseline | Codes are kept numeric, so the 23-feature contract matches the form and the comparison against the earlier draft stays meaningful. The limitation is stated below. |
| Feature scaling | `StandardScaler` for logistic regression only, fitted on the training rows | Coefficients need comparable scales; trees split on order, so scaling cannot change a fitted tree. |
| Outlier treatment | None | The tails are real accounts, not errors. Removing them would change the population the model describes. Ranges are enforced instead (§8.3). |
| Class imbalance handling | No resampling, no SMOTE, no re-weighting | The imbalance is handled at the evaluation and reporting level: F1 and recall drive selection, the baseline is reported beside every model, and the threshold is fixed and stated. |
| Leakage control | The split happens first; every transform is fitted on `X_train` only | Asserted numerically: the fitted scaler's mean is 167,364.666667, exactly the training mean, not the full-dataset mean of 167,484.322667 (`models/metrics.json` `checks.leakage`). |

The no-resampling decision is worth defending explicitly, because it is the choice a reader is
most likely to question. Resampling the training rows changes the prior the model learns, which
changes the meaning of the probability the UI displays. The system shows an uncalibrated
probability and a fixed 0.5 threshold; synthesising rows would make both harder to explain
without evidence that it improves the metric that matters. The honest trade-off is reported
instead: recall 0.3557, precision 0.6611, and a confusion matrix showing 855 missed defaulters
(§12).

## 8.2 The split

```python
train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
```

24,000 training rows and 6,000 held-out rows, each side carrying the 77.88 / 22.12 class mix:
training 18,691 / 5,309, held-out 4,673 / 1,327. `random_state=42` is recorded in
`models/metrics.json`. The held-out rows are scored **once**, after selection, by
`ml/evaluate.py`; the selection rule itself runs on training rows only.

## 8.3 Validation, and where the boundaries come from

`src/validation.py` enforces the contract in two places: a CSV validator for uploads (25 columns,
exact order, target in `{0,1}`, documented code sets, hard floors such as `LIMIT_BAL >= 1` and
`PAY_AMT* >= 0`) and a single-record validator for the 23 form features. The hard boundaries are
deliberately wider than the observed sample — `18 <= AGE <= 100`, `PAY_*` legal set −2…9 — because
a legitimate future upload must not be rejected for falling outside 2005's observed range. The
observed range is descriptive, not a contract. This deviation from a stricter reading of the
blueprint is recorded as D9 and D10 in `docs/architecture.md` §9.

## 8.4 The limitation this section must carry

`EDUCATION` and `MARRIAGE` are **not ordinal**: code 2 ("university") is not twice code 1
("graduate school"). A linear model can only fit a straight-line effect on those codes, and the
observed default rates are non-monotone (education code 3: 25.16%, code 4: 5.69%, code 5: 6.43%),
which is direct evidence that a straight line describes them poorly. A one-hot variant is a
legitimate improvement and is named in §23; it was not part of the delivered baseline, and this
report does not claim the baseline handled those codes well.

## Evidence

- `docs/preprocessing_contract.md`
- `evidence/s0/inspect_dataset.txt`
- `evidence/s2/inspect_dataset.txt`
- `evidence/s2/pytest_test_schema.txt`
- `models/metrics.json`
- `ml/train.py`
- `src/validation.py`
- `docs/architecture.md`
- `models/eda/summary.json`
