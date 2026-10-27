# Model card — AI Hub Campus default-risk classifier

The shipped artifact, described for the people who will operate, mark, audit or inherit it.
Every number here is read from `models/model_manifest.json` and `models/metrics.json` — the files
the application itself verifies at startup — and every claim names the command that reproduces it.
`docs/RELEASE_NOTES.md` points here from the release record.

| | |
|---|---|
| Artifact | `models/best_pipeline.joblib` (joblib, scikit-learn `Pipeline`) |
| Artifact SHA-256 | `48ce02563b2aad9fbf9397603c642b0319be617c57fde8e1fd26ec08d518ad7b` |
| Artifact size | 8,187 bytes |
| Model version | `aihubcampus-default-risk-1+48ce02563b2a` (the version is derived from the artifact hash: a retrained artifact is a new version) |
| Estimator | `DecisionTreeClassifier(max_depth=5, random_state=42)` |
| Transform | passthrough — a tree splits on order, not distance |
| Positive class | `1` = "Predicted default next month" |
| Decision threshold | `0.5`, fixed at the evaluated value |
| Selected by | highest mean 5-fold cross-validated F1 on the training rows only; the held-out test set played no part in the choice (`test_rows_used_for_selection: 0`) |
| Trained | `2026-10-26T08:59:51Z` by `ml/train.py` → `ml/evaluate.py` |
| Sprint | S4 |

## 1. What it does

Given the 23 account features of one credit-card client, it returns the model's estimated
probability that the client defaults on the next month's payment, and the class implied by the
0.5 threshold. The application renders that probability with a risk band, plain-language advice,
the measured false-negative rate and a disclaimer (`src/inference.py`).

The probability is **uncalibrated**: no calibration test has been run, so it is the model's own
score, not a real-world risk percentage. The result screen says so on every prediction.

## 2. Intended use

- **Academic demonstration** of an end-to-end data-science system: dataset → EDA → training →
  evaluation → a web application with role-based access, for a university group assignment.
- **Decision support with a human in the loop**, on the public 2005 Taiwanese dataset
  (UCI *Default of Credit Card Clients*).
- **Teaching material** for how a model's limits are disclosed to a user.

## 3. Out of scope — do not use it for

- Real credit decisions, limit changes, collections or any action against a person. No limit is
  frozen, no application is rejected and nothing is reported about anyone by this system.
- Real customer data of any kind. The form says "do not enter real customer data", and the
  dataset is a public 2005 sample from a different market and a different decade.
- Any automated sanction. The risk band is an illustrative UI cutoff, not a validated banking
  threshold and not a regulatory credit grade.
- Populations, products or periods other than the one sampled: no external validation has been
  performed, and none of the metrics below transfer to another bank, country or year.

## 4. Training data

| | |
|---|---|
| Source | `data/UCI_Credit_Card.csv`, UCI *Default of Credit Card Clients* (Taiwan, 2005) |
| Dataset SHA-256 | `a0f0ab49d6326671d6cd83be5c88dcf18007025fe9a53ecd699119c871176ca1` |
| Rows × columns | 30,000 × 25 |
| Class balance | 23,364 (77.88%) no default · 6,636 (22.12%) default |
| Features used | 23 — the target and `ID` are dropped |
| Split | `train_test_split(test_size=0.2, stratify=y, random_state=42)` → 24,000 train / 6,000 test; test holds 4,673 / 1,327 |
| Preprocessing | none fitted on the test set; the pipeline is a passthrough into the tree |

Feature order is contractual: `ml/schema.py:FEATURES`, repeated verbatim in
`models/model_manifest.json["features"]["order"]`, and the application assembles every request in
that order (`src/inference.py`). A mismatch is a release-stopping defect, and
`ml/verify_artifact.py` fails the startup if the two ever disagree.

The 23 features: `LIMIT_BAL, SEX, EDUCATION, MARRIAGE, AGE, PAY_0, PAY_2…PAY_6, BILL_AMT1…BILL_AMT6,
PAY_AMT1…PAY_AMT6`. Units and legal code sets are documented in `docs/data_dictionary.md` and
enforced by `src/validation.py` before the model is called.

## 5. Evaluation — held-out 6,000 accounts, threshold 0.50

| Model | Accuracy | Precision | Recall | F1 | ROC AUC |
|---|---:|---:|---:|---:|---:|
| **Decision tree (shipped)** | **0.8172** | **0.6611** | **0.3557** | **0.4625** | **0.7423** |
| Random forest | 0.8122 | 0.6773 | 0.2879 | 0.4040 | 0.7665 |
| Logistic regression | 0.8077 | 0.6868 | 0.2396 | 0.3553 | 0.7076 |
| Baseline (always "no default") | 0.7788 | 0.0000 | 0.0000 | 0.0000 | — |

Confusion matrix of the shipped model: TN 4,431 · FP 242 · FN 855 · TP 472 (total 6,000). The
recorded metrics are consistent with that matrix to 0.0 absolute delta
(`metrics.json.evaluation.models.decision_tree.arithmetic_check`).

**The number that matters most is the recall: 0.3557.** At the 0.5 threshold the model misses
855 of the 1,327 accounts that actually defaulted — 64.4% of them. A "no default" answer
therefore does not rule out default, and the application prints that sentence with every result.
Accuracy of 0.8172 must be read against the 0.7788 that a constant "no default" answer reaches on
the same split; the honest gain is 3.8 percentage points, not 81.7% of anything.

## 6. Known limitations

1. **Low recall for the class that matters (0.3557).** Chosen deliberately: F1 on the default
   class was the selection objective, because accuracy is dominated by the majority class. The
   trade is disclosed in the UI, in `docs/report/12_evaluation.md` and here.
2. **Uncalibrated probability.** No calibration curve, no Brier score, no reliability test. Read
   the number as a ranking score.
3. **Single split, single seed.** One stratified 80/20 split at `random_state=42`; the five CV
   folds are reported in `metrics.json`, but no repeated-split or nested-CV estimate exists.
4. **No external validation.** Trained and tested on one 2005 Taiwanese sample. No evidence of
   transfer to another population, product or period.
5. **Fairness not audited.** `SEX`, `EDUCATION`, `MARRIAGE` and `AGE` are inputs. Group-level
   error rates were not measured, so no fairness claim of any kind is made.
6. **Shallow tree.** `max_depth=5` for interpretability; the random forest scores a higher ROC
   AUC (0.7665) and was not selected because selection was on CV F1.
7. **No drift monitoring.** Nothing watches the input distribution or the outcome; retraining is
   a manual act (see §8).

## 7. How to verify the artifact

Run from the repository root, or inside the container (the paths are the same):

```bash
python ml/verify_artifact.py                 # dataset identity, feature contract, class
                                             # semantics, pickle allowlist, pipeline schema,
                                             # determinism, metrics consistency
python -m src.inference --input request.json # one scored request, as JSON, from the verified
                                             # pipeline — the same path the UI uses
```

`ml/verify_artifact.py` must print `RESULT: PASS`; the app calls it at startup and refuses to
serve if it fails. The full transcript for this release is `evidence/s5/` and the parity check
between the UI and the pipeline is `evidence/s16/live_smoke.txt`.

## 8. Retraining and change control

```bash
python -m ml.train --csv data/UCI_Credit_Card.csv --out models     # retrain the three candidates
python -m ml.evaluate --models-dir models                          # held-out metrics, figures
python -m ml.verify_artifact --models-dir models                   # the artifact gate
```

Retraining replaces `models/best_pipeline.joblib`, which changes its SHA-256, which changes the
model version string, which is visible on every result screen and in `prediction_logs`. A new
artifact needs its own evaluation record and its own release: the version string is the only
thing tying a stored prediction to the model that produced it.

## 9. Ownership and contact

Academic group project for the AI Hub Campus assignment. The operator of
`www.aihubcampus.online` is the owner of the deployment; `docs/runbook.md` §10 is the handover
section, and `PROJECT_DETAILS.md` (git-ignored) holds the human contact list.
