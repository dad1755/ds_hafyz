# 11. Model Training

Draft, Sprint 14. This section describes what was actually fitted, on which rows, with which
settings, and what the training-time evidence was. Numbers are from `models/metrics.json`; the
verbatim run output is `evidence/s4/train.txt`.

## 11.1 The training rows

Stratified 80/20 split with `random_state=42`: **24,000** training rows (18,691 class 0, 5,309
class 1) and **6,000** held-out rows (4,673 class 0, 1,327 class 1). Both sides carry the seed's
class mix to within rounding, which is what stratification is for.

## 11.2 Cross-validation, on training rows only

`StratifiedKFold(n_splits=5, shuffle=True, random_state=42)` over the 24,000 training rows. No
fold touches a held-out row. Results, mean with standard deviation across folds:

| Candidate | CV F1 | CV precision | CV recall | CV ROC-AUC |
|---|---|---|---|---|
| Decision tree | **0.4643 ± 0.0138** | 0.6868 ± 0.0190 | 0.3513 ± 0.0186 | 0.7555 ± 0.0057 |
| Random forest | 0.4191 ± 0.0153 | 0.6959 ± 0.0204 | 0.3001 ± 0.0141 | 0.7765 ± 0.0028 |
| Logistic regression | 0.3647 ± 0.0139 | 0.7118 ± 0.0165 | 0.2452 ± 0.0113 | 0.7261 ± 0.0111 |

Two observations the report must make rather than skip:

- The ranking by F1 and the ranking by ROC-AUC disagree. The random forest has the best AUC
  (0.7765) and the worst-of-two recall (0.3001). AUC measures ranking across all thresholds; the
  system operates at one fixed threshold and cares about the default class, so F1 at 0.5 is the
  criterion that matches the deployed behaviour. The disagreement is a real finding, not noise,
  and it is reported in §19.
- The F1 gaps between candidates (0.4643 vs 0.4191 vs 0.3647) are larger than the fold standard
  deviations (≈0.014–0.015), so the ordering is not an artefact of fold noise — unlike, for
  example, a 0.002 gap, which this report would refuse to call a difference.

## 11.3 The selected model

`selection.selected` = `decision_tree`, `decided_by` = `cv_f1`. The selected pipeline is refitted
on the full 24,000 training rows and written as `models/best_pipeline.joblib` — 8,187 bytes,
SHA-256 `48ce02563b2aad9fbf9397603c642b0319be617c57fde8e1fd26ec08d518ad7b`. The artifact is
asserted to reproduce its candidate's test predictions and probabilities exactly
(`checks.artifact.predictions_identical_to_candidate` is true), so the shipped file is the model
that was evaluated, not a retrained lookalike.

The model version string is `aihubcampus-default-risk-1+48ce02563b2a` — the first 12 hex characters
of the artifact digest, so a replaced artifact cannot keep the old version.

## 11.4 What training did not do

No training happens at runtime. `src/inference.py` has no `fit` path, and the dataset manager
imports no training or serialisation module: an upload stages a dataset version and records
`retraining_triggered: false` (`evidence/s9/probe_datasets.txt`). Retraining is an explicit offline act
(§23.1).

## Evidence

- `models/metrics.json`
- `models/best_pipeline.joblib`
- `models/model_manifest.json`
- `evidence/s4/train.txt`
- `evidence/s4/determinism.txt`
- `evidence/s4/contract_checks.txt`
- `evidence/s9/hygiene.txt`
- `src/inference.py`
