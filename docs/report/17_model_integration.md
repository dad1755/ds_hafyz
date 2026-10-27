# 17. Predictive Model Integration

Draft, Sprint 14. Contract: `docs/inference_contract.md`. Implementation: `src/inference.py`,
`ml/verify_artifact.py`. Evidence: `evidence/s5/`, `evidence/s11/restart.txt`.

## 17.1 Three files, one trusted artifact

| File | Role |
|---|---|
| `models/best_pipeline.joblib` | The selected fitted `Pipeline` (transform + estimator). The only model the app may load. 8,187 bytes, SHA-256 `48ce02563b2aad9fbf9397603c642b0319be617c57fde8e1fd26ec08d518ad7b`. |
| `models/model_manifest.json` | The contract the artifact is checked against: ordered features, class labels and caveats, threshold, model version, dataset and artifact checksums. |
| `models/metrics.json` | The full evaluation record the admin panel renders. |

All three ship read-only in the image at `/app/models` (root-owned, mode 644) while the container
runs as `app`: the runtime can read them and cannot rewrite them.

## 17.2 Verify before load — eleven checks

`python -m ml.verify_artifact --models-dir models` runs eleven ordered checks and exits non-zero
with every failure named: files present, manifest schema, artifact checksum, artifact provenance,
dataset identity, feature contract, class semantics, pickle allowlist, pipeline schema,
deterministic self-check, metrics consistency.

The eighth check is the one that answers "was this file produced by trusted code?". `joblib`/`pickle`
cannot be authenticated, so trust is established two ways: the bytes must be the ones the manifest
records, and every class the pickle references must come from `numpy`/`sklearn`/`joblib`/`pandas`/
`scipy` plus a small set of `builtins` constructors. Both are enforced by the same restricted
unpickler that loads the object, and `src/inference.py` has no other load path — so a check cannot
be bypassed by loading the file another way.

## 17.3 The service

```python
from src.inference import load_service
service = load_service()          # verify + load once per process (cached on the resolved dir)
result  = service.predict(features)
```

`predict` validates with the 23-feature contract first, assembles a one-row frame in manifest order,
and calls `predict_proba` on the already-fitted pipeline. There is no `fit`, no partial fit, no reload
during a request, no upload path for a joblib file, and no code path that trains.

## 17.4 Agreement between screen, CLI and pipeline

The screen is not a second implementation. For the same 23 values, the page's class, probability and
band equal the direct pipeline's output — the probability is compared with `repr()`, not a tolerance,
over six distinct synthetic rows (T09), and the CLI path agrees as well
(`evidence/s5/cli_vs_pipeline.txt`). The demonstrator row is recorded end to end: class `1`,
probability `0.7195348837209302`, band `High`, version `aihubcampus-default-risk-1+48ce02563b2a`.

## 17.5 The band mapping, and its boundary behaviour

| Estimated P(default) | Band | Advice |
|---|---|---|
| 0.00 – 0.2499 | Low | Continue routine repayment reminders and periodic review. |
| 0.25 – 0.4999 | Watch | Review payment schedule and contact the customer with a neutral reminder. |
| 0.50 – 0.7499 | High | Offer supportive contact and discuss potential payment arrangements. |
| 0.75 – 1.00 | Critical | Prioritise a supportive conversation and a payment plan; escalate for human review. |

The cutoffs belong to the upper band (`0.25 → watch`, `0.50 → high`, `0.75 → critical`). T10 records
nine edge cases (`0.0, 0.2499, 0.25, 0.4999, 0.50, 0.7499, 0.75, 0.9999, 1.0`) mapping to
`low, low, watch, watch, high, high, critical, critical, critical`, and a 10,001-point sweep from 0.0
to 1.0 that matches exactly one band at every point, never skips a band and never goes backwards.
Advice text is read from the band object, not retyped by the page.

These bands are illustrative UI ranges, not validated banking thresholds. The report must not
present them as calibrated risk grades.

## 17.6 Survival across restarts

T11 is proven twice: at unit level, a second process resolves the pre-restart session token and
re-verifies the artifact with the same `model_version` and a 64-hex `artifact_sha256`; at deployment
level, `docker compose up -d --force-recreate web` keeps every row and re-passes all eleven checks
with `artifact_sha256 48ce02563b2aad9f…` before and after (`evidence/s11/restart.txt`).

## Evidence

- `docs/inference_contract.md`
- `src/inference.py`
- `ml/verify_artifact.py`
- `models/model_manifest.json`
- `models/best_pipeline.joblib`
- `models/metrics.json`
- `evidence/s5/verify_artifact.txt`
- `evidence/s5/cli_vs_pipeline.txt`
- `evidence/s5/boundaries.txt`
- `evidence/s5/tamper.txt`
- `evidence/s11/restart.txt`
- `evidence/s11/test-results/demo_prediction.txt`
- `docs/test_matrix.md`
