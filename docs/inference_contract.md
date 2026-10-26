# Inference contract — S5

What the application is allowed to do with the model, and what every prediction result must
say. Written at S5 so S7 (the prediction UI) and S10 (the admin evaluation panel) build on a
fixed contract instead of inventing one.

Source of truth: `blueprint.md` §5 steps 7–10 and the recommendation table, §4 feature
contract, §9 SPRINT 5. Where this document and the blueprint disagree, the blueprint wins.

## 1. The three shipped files

| File | What it is | Who writes it |
|---|---|---|
| `models/best_pipeline.joblib` | The selected, fully fitted scikit-learn `Pipeline` (transform + estimator). The only model the app may load. | `ml/evaluate.py` |
| `models/model_manifest.json` | The contract the artifact is checked against: ordered 23 features, class labels and caveats, threshold, model version, dataset and artifact checksums, evaluation summary. | `ml/evaluate.py` |
| `models/metrics.json` | The full evaluation record: split counts, seeds, hyperparameters, all metrics, confusion matrices, package versions. | `ml/evaluate.py` |

All three are committed. The image ships all three read-only (root-owned, mode 644) at
`/app/models`; the container runs as `app`, so the runtime can read them and cannot rewrite
them. `models/candidates/`, `models/eda/` and `models/figures/` are not shipped.

The model version is `aihubcampus-default-risk-1+<first 12 hex of the artifact sha256>`, so a
retrained or replaced artifact cannot keep the old version string.

## 2. Verify before load

`python -m ml.verify_artifact --models-dir models` runs eleven ordered checks and exits 1 with
every failure named. It never returns a partially trusted pipeline: a check that fails stops
the run before the pickle is deserialised, and `--json` gives the same report machine-readable.

| # | Check | Fails when |
|---|---|---|
| 1 | `files_present` | the manifest or the artifact is missing, or is a symlink |
| 2 | `manifest_schema` | `schema_version` is unsupported or a section is missing |
| 3 | `artifact_checksum` | the artifact's sha256 or byte count is not the manifest's |
| 4 | `artifact_provenance` | the recorded creation path is not `ml/train.py → ml/evaluate.py`, or the file is not an uncompressed joblib pickle |
| 5 | `dataset_identity` | the manifest's dataset sha256 is not the immutable seed's, or the CSV on disk has changed |
| 6 | `feature_contract` | the ordered features are not `ml.schema.FEATURES`, the count is not 23, or `ID`/target is among them |
| 7 | `class_semantics` | the class labels, caveats or probability label differ from the documented wording, the threshold is not 0.5, the positive class is not 1, or no version is recorded |
| 8 | `pickle_allowlist` | the pickle references any class outside `numpy`/`sklearn`/`joblib`/`pandas`/`scipy` and a small set of `builtins` constructors |
| 9 | `pipeline_schema` | the object is not a `Pipeline(transform, model)`, its transform does not select the manifest's ordered features, or it has no `predict_proba` over `[0, 1]` |
| 10 | `deterministic_self_check` | one fixed probe row does not score identically twice, or its probability/class is inconsistent with the threshold |
| 11 | `metrics_consistency` | `metrics.json` names a different artifact, model or threshold (skipped with a note when `metrics.json` is absent) |

Check 8 is the "not produced by trusted code" check. `joblib`/`pickle` cannot be
authenticated, so trust is established two ways: the bytes must be the ones the manifest
records (check 3), and the classes the pickle references must all come from the scientific
stack (check 8). Both are enforced by the same restricted unpickler that loads the object, so
a check cannot be bypassed by loading the file another way — `src/inference.py` has no other
load path.

## 3. The service

```python
from src.inference import load_service

service = load_service()                     # verify + load once per process (cached)
result  = service.predict(features)          # dict of the 23 features
```

* `load_service(models_dir=None)` — `models_dir` is process configuration, never a request
  value. The resolved directory is the cache key, so the artifact is loaded once.
* `predict(features)` — validates with `src.validation.validate_features` (the S2 contract:
  all 23 features, whole numbers, legal code sets, documented ranges), assembles a one-row
  frame in **manifest order**, and calls `predict_proba` on the already-fitted pipeline.
  Raises `ValidationError` before the model is touched when the input is invalid.
* There is no `fit`, no partial fit and no reload during a request; there is no API that
  accepts an uploaded joblib, and no code path that trains.
* `PredictionResult` is frozen and carries every disclosure (see §5).

Negative statement balances (`BILL_AMT1…6`) are valid and accepted; `PAY_AMT1…6` are
non-negative; `PAY_0…PAY_6` accept the documented codes −2…9.

## 4. Risk bands (illustrative, not regulatory)

| Estimated P(default) | Band | Advice |
|---|---|---|
| 0.00 – 0.2499 | Low | Continue routine repayment reminders and periodic review. |
| 0.25 – 0.4999 | Watch | Review payment schedule and contact customer proactively with a neutral reminder. |
| 0.50 – 0.7499 | High | Offer supportive contact and discuss potential payment arrangements. |
| 0.75 – 1.00 | Critical | Recommend human risk/support specialist review before any action. |

`src/recommendations.py` implements the four bands as half-open intervals `[lower, upper)`
with the top band closing at 1.0, so the mapping is **continuous and gapless**: every value
in `[0, 1]` falls in exactly one band, and 0.25, 0.50 and 0.75 belong to the band *above*
them. The bands are illustrative UI cutoffs — not validated banking thresholds, not
regulatory credit grades, and never an automated sanction: no limit is frozen, no application
is rejected and no customer is penalised without a human review.

The predicted **class** is not derived from the bands: it is `probability >= 0.5`, the
threshold fixed at evaluation time (a different threshold needs train/validation-only
selection and its own evaluation evidence).

## 5. Wording that must appear on every result

| Field | Text |
|---|---|
| class 0 label | `Predicted non-default next month` — **not** a guarantee of payment |
| class 1 label | `Predicted default next month` — **not** a confirmed delinquency |
| probability label | `Estimated model probability of next-month default` |
| calibration | `The probability is uncalibrated — no calibration test has been run — so read it as the model's own score, not as a real-world risk percentage.` |
| false negatives | the measured recall from `metrics.json` (0.36 at threshold 0.50: 64.4% of the 1,327 held-out defaulters were missed) — a non-default prediction does not rule out default |
| model version | `Model version: aihubcampus-default-risk-1+<sha256[:12]>` |
| disclaimer | academic demonstration on 2005 Taiwanese data; not financial advice, not a credit decision, not an automated sanction; do not enter real customer data |

`PredictionResult.as_dict()` and `PredictionResult.display_lines()` always contain all of the
above — there is no result path that omits the disclaimer or the model version, and
`tests/test_prediction.py` asserts it for all four bands and both classes.

## 6. Acceptance evidence

| Claim | Evidence |
|---|---|
| direct pipeline, service and CLI agree byte for byte on ≥5 inputs | `evidence/s5/cli_vs_pipeline.txt` (`tests/test_prediction.py`) |
| cutoffs 0.25 / 0.50 / 0.75 behave, and the bands are gapless | `evidence/s5/boundaries.txt` |
| the artifact matches its manifest, and tampering is rejected | `evidence/s5/verify_artifact.txt`, `evidence/s5/tamper.txt` |
| the image ships the artifacts read-only and can verify them | `evidence/s5/image_artifact.txt` |
| the app loads the verified pipeline | `evidence/s5/app_loads_model.txt` |
| nothing trains at request time | `tests/test_prediction.py::test_prediction_never_fits_the_pipeline`, `::test_prediction_does_not_reload_or_reverify_the_artifact` |
