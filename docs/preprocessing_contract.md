# Preprocessing contract — what Sprint 4 must implement

Status: **design, fixed at the end of Sprint 3.** Nothing here trains a model. S4 implements
exactly this contract and records the produced numbers in `models/metrics.json`; any deviation
must be written back into this file in the same commit, with the reason.

The contract exists so that three things cannot drift apart: the column contract
(`ml/schema.py`), the training split, and the transform used at prediction time.

---

## 1. Inputs

| Item | Rule |
|---|---|
| Source | `data/UCI_Credit_Card.csv`, SHA-256 `a0f0ab49…176ca1`, used unmodified |
| Rows | 30,000 accounts |
| Features | The 23 names in `ml.schema.FEATURES`, **in that order** |
| Dropped | `ID` (technical identifier — never a feature) |
| Target | `default.payment.next.month`, values `{0, 1}` only; 1 = default next month |
| Validation | A frame must pass `src.validation.validate_dataframe` before it is split |

`ID` and the target are removed before anything is fitted. No column is added, renamed or
recomputed in S4: the model input is the 23 documented features, which is also what the
prediction form will collect (S7).

## 2. Split

```python
train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
```

- **Stratified 80/20** → 24,000 train / 6,000 test rows, each side carrying the seed's
  77.88 % / 22.12 % class mix. S4 records the *actual* per-side class counts in
  `metrics.json`; this document does not pre-compute them.
- **`random_state=42`** everywhere, and the value is written into `metrics.json`. 42 is a
  reproducibility choice, not an attempt to reproduce the draft's numbers.
- The test set is touched **once**, at the end, for the final comparison. Model selection and
  any hyper-parameter choice happen on the training set only (train-only cross-validation).
  No tuning against the test set.
- No resampling, no SMOTE, no class re-weighting before the split. If S4 uses
  `class_weight="balanced"`, it is a documented hyper-parameter of one candidate, chosen
  inside the training folds, and stated in `metrics.json`.

## 3. Transform — fitted on train only

```text
Pipeline(
  transform  = ColumnTransformer([...])   # fitted on X_train only
  estimator  = LogisticRegression | DecisionTreeClassifier | RandomForestClassifier
)
```

Rules, in order of importance:

1. **One `Pipeline` object per candidate model**, with the `ColumnTransformer` as its first
   step. The split happens first; the pipeline is fitted on `X_train`; the test set is only
   ever `transform`ed. `fit_transform` is never called on the full dataset.
2. **Named steps** (`"transform"`, `"model"` or explicit column-transformer keys) so the saved
   artifact is inspectable and the feature order is checkable.
3. **No target-derived input.** No encoding, imputation, binning or scaling computed from `y`,
   and nothing computed from the test rows.
4. **The same object transforms at inference.** `models/best_pipeline.joblib` holds the fitted
   `ColumnTransformer` *inside* the pipeline. Serving never re-implements scaling or encoding;
   it calls `pipeline.predict` / `pipeline.predict_proba` on a 23-column frame in
   `FEATURES` order.

### 3.1 Scaling differs by model, on purpose

| Candidate | Numeric treatment | Why |
|---|---|---|
| `LogisticRegression` | `StandardScaler()` fitted on train | Coefficients and solver convergence need comparable scales; `LIMIT_BAL` (10³–10⁶ NTD) would otherwise dominate |
| `DecisionTreeClassifier(max_depth=5)` | passthrough (`"passthrough"`) | A tree splits on order, not distance; scaling is a monotone transform and cannot change the fitted tree |
| `RandomForestClassifier(n_estimators=100, max_depth=5)` | passthrough | Same reason as the tree |

The difference is deliberate and must be **stated in the report**, not smoothed over: the
three candidates are not "the same pipeline with a different last step". Each is a fair,
leakage-free pipeline for its own estimator, which is what the comparison claims.

`LogisticRegression` uses `max_iter=1000` (documented; the default 100 warns on this data) and
`random_state=42` where the estimator accepts one.

### 3.2 Categorical codes — the decision, and its limitation

`SEX`, `EDUCATION`, `MARRIAGE` and `PAY_0…PAY_6` arrive as integer codes and are **kept
numeric** in the S4 baseline: no one-hot encoding. Reasons:

- The dataset ships codes, the 23-feature contract is numeric, and the v3 draft that the
  report compares against treats them as numeric. Changing that here would make the
  `claimed` vs `reproduced` comparison in S4 meaningless.
- `PAY_*` codes are genuinely ordered (payment delay in months), so a numeric treatment is
  defensible.
- Keeping one numeric block means one transformer shape for all three candidates, which
  keeps the comparison fair.

Limitation, which must appear in the report: `EDUCATION` and `MARRIAGE` are **not** ordinal —
code 2 ("university") is not twice code 1 ("graduate school"). A linear model can only fit a
straight-line effect on those codes, and the observed non-monotone default rates (see
`docs/report_evidence.md` §6.3) are evidence that a straight line is a poor description. If S4
adds a one-hot variant it must be an *additional, separately named* candidate, and if such a
model is selected the served artifact must contain the same one-hot transformer.

## 4. Target and threshold

- Positive class is **1 = default next month**. Precision/recall/F1 are computed for label 1.
- Decision threshold is **0.5** — the evaluated value, recorded in
  `models/model_manifest.json`. Alternative thresholds need train/validation-only selection
  and their own evaluation evidence; the UI never silently shifts the threshold.
- The always-class-0 baseline (accuracy 77.88 %) is computed on the same test rows and
  reported beside every model. A model that does not beat it on the metrics that matter
  (default-class recall and F1) is not an improvement.

## 5. What S4 must produce

| Artifact | Content |
|---|---|
| `ml/train.py` | Builds the split, the three pipelines, fits on train only, selects on train-only CV |
| `ml/evaluate.py` | Final metrics on the untouched test set, confusion matrices, baseline comparison |
| `models/best_pipeline.joblib` | The selected **complete** pipeline (transform + model) |
| `models/metrics.json` | Dataset SHA-256, seeds, split counts, hyper-parameters, per-model metrics, confusion matrix totals, package versions |
| `models/model_manifest.json` | Ordered feature list, class semantics, threshold, transform description, artifact checksum |

## 6. Checks S4 must pass before it claims anything

1. **Rerun determinism** — same environment, same seed → identical metrics (floating
   tolerance only).
2. **Leakage check** — the transform step fitted on train is the one applied to test; assert
   that a scaler's `mean_` matches `X_train` statistics, not the full dataset's.
3. **Arithmetic consistency** — accuracy, precision, recall and F1 recomputed from the
   confusion matrix's TN/FP/FN/TP totals (6,000 test rows) and matching `metrics.json`.
4. **Order check** — the manifest's feature order equals `ml.schema.FEATURES`, and the saved
   pipeline scores a 23-column frame in that order.
5. **No placeholder** — every number in `metrics.json` is produced by the run recorded under
   `evidence/s4/`.

## 7. Explicit non-goals for S4

No deep learning, no LLM, no paid API, no runtime training on a prediction request, no
PostgreSQL/Redis/Celery, no pickle/joblib upload path, no automatic retraining when an admin
uploads a dataset (S9 stages a dataset; the deployed model changes only through an explicit,
approved rebuild).
