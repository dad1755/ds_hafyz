# 10. Machine Learning Methodology

Draft, Sprint 14. The methodology is fixed in `docs/preprocessing_contract.md` and implemented in
`ml/train.py` and `ml/evaluate.py`; every number quoted here is from `models/metrics.json`.

## 10.1 Task and target

Binary classification. Positive class = 1 = default on the next payment; negative class = 0 = no
default. The 23 features are `ml.schema.FEATURES`, in that order, and the order is part of the
contract: the shipped pipeline is asserted to consume a 23-column frame in that order
(`models/metrics.json` `checks.feature_order`).

## 10.2 Three candidates, each a complete pipeline

Each candidate is a scikit-learn `Pipeline` whose first step is a column transform and whose last
step is the estimator. The split happens before fitting; the pipeline is fitted on `X_train` only;
the test rows are only ever transformed. Three algorithms were chosen to span the obvious
trade-off between interpretability and flexibility:

| Candidate | Estimator | Hyperparameters | Numeric treatment |
|---|---|---|---|
| Logistic regression | `LogisticRegression` | `max_iter=1000`, `random_state=42` | `StandardScaler` fitted on train |
| Decision tree | `DecisionTreeClassifier` | `max_depth=5`, `random_state=42` | passthrough |
| Random forest | `RandomForestClassifier` | `n_estimators=100`, `max_depth=5`, `random_state=42` | passthrough |

The scaling difference is deliberate and is stated rather than smoothed over: a tree splits on
order, so a monotone transform cannot change the fitted tree, while a linear model needs
comparable scales or `LIMIT_BAL` (10³–10⁶ NTD) dominates the fit. The comparison is therefore not
"the same pipeline with a different last step"; each is a fair pipeline for its own estimator.

`max_depth=5` was chosen before the run as a regularisation choice, not tuned against the test
set. That is a real limitation of the study: no systematic hyperparameter search was performed, so
the comparison measures three sensible defaults rather than three optimised models.

## 10.3 Selection rule, fixed before the results were seen

Selection maximises **mean five-fold cross-validated F1 on class 1 over the 24,000 training rows
only**. F1 is primary because accuracy is dominated by the majority class; F1 balances recall
against the precision cost. Ties within 0.005 absolute CV F1 are broken by higher mean CV recall,
then higher mean CV precision. A candidate whose mean CV F1 is not above zero is ineligible.

The held-out 6,000 rows play **no part** in the choice: `selection.test_rows_used_for_selection`
is 0 in `models/metrics.json`. This is the single most important methodological claim in the
section, and it is recorded as a number rather than promised in prose.

## 10.4 What was deliberately not done

- **No test-set tuning.** The held-out set is scored once, after selection.
- **No resampling or class weighting.** The prior the model learns is the real prior, so the
  displayed probability means what the report says it means (§8.1).
- **No threshold optimisation.** The threshold is 0.5 and is shown on every result. Choosing a
  lower threshold would raise recall and lower precision, but it would need validation-only
  evidence this project did not produce.
- **No deep learning, no LLM, no paid API.** The task does not need them and the brief forbids
  them.
- **No feature engineering beyond the documented contract.** No interaction terms, no binning, no
  target encoding — each would need its own leakage argument.

## 10.5 Reproducibility

The environment is pinned: Python 3.12.14, scikit-learn 1.9.1, numpy 2.5.4, pandas 3.1.0, joblib
1.6.0, as recorded in `models/metrics.json` `environment`. A second independent run into a
separate output directory reproduced `metrics.json` identically across 208 numeric fields and
produced byte-identical artifacts and figures (`evidence/s4/determinism.txt`).

## Evidence

- `docs/preprocessing_contract.md`
- `ml/train.py`
- `ml/evaluate.py`
- `models/metrics.json`
- `ml/schema.py`
- `evidence/s4/train.txt`
- `evidence/s4/evaluate.txt`
- `evidence/s4/determinism.txt`
- `evidence/s4/contract_checks.txt`
