# 23. Future Enhancements

Draft, Sprint 14. Each item names what would have to be built and how it would be checked. None of
these is claimed as done.

## 23.1 Retraining as an explicit, governed act

The dataset manager already stages and activates dataset versions without touching the model, and
every upload records `retraining_triggered: false`. The natural next step is a governed retrain: a
script that reads the active dataset version, refits the three candidates, writes a new artifact
with a new checksum-derived version string, and produces a comparison against the deployed metrics
before anyone promotes it. Check: the artifact verifier's eleven checks pass on the new file and the
version string changes; the old artifact remains loadable until promotion.

## 23.2 Calibration and threshold policy

Produce a reliability curve and a Brier score on validation rows, and choose the operating threshold
against a stated cost ratio rather than fixing 0.5. Check: calibration metrics recorded in
`metrics.json`; the UI displays the chosen threshold and the recall/precision it implies; the
selection uses validation rows only, never the held-out set.

## 23.3 Fairness analysis and a demographic ablation

Compute subgroup confusion matrices and equal-opportunity gaps for the protected attributes, then fit
and evaluate a variant without `SEX`, `MARRIAGE` and `EDUCATION`, and report the accuracy/recall cost
of removing them. Check: a table of per-group recall and precision beside the full-model figures, and
a documented decision about which variant ships. This is the largest ethical gap in the current
system (§20.3) and should be the first enhancement attempted.

## 23.4 A stronger model, evaluated on the same terms

Gradient boosting and a one-hot encoding of the non-ordinal codes are the obvious candidates. Check:
the same selection rule, the same held-out set, the same arithmetic and baseline checks, and a
comparison table that includes the current tree so the improvement is visible rather than asserted.

## 23.5 Explainability for the individual prediction

The evaluation panel explains the model globally (importances, confusion matrices). A per-prediction
explanation — which features pushed this account's score up or down — would help a human reviewer
more. Check: a deterministic attribution (for example SHAP or the tree's own decision path) rendered
beside the result, with a test that the explanation is stable for the same input.

## 23.6 Session model and edge settings

Fix the three recorded deployment findings: set a real session cookie with `Secure` and `SameSite`
so a hard refresh does not sign the user out (F-1), and enable the zone's "Always Use HTTPS" so
`http://` redirects (F-2, F-3). Check: the browser journey survives `page.reload()` while still
signed in, the XSRF cookie is `Secure`, and `http://` returns a 301/308 with a `Location` header.

## 23.7 Operations

Retention policy for audit and prediction rows, structured log shipping, an alert on healthcheck
failure, and a scheduled restore drill. Check: a purge job with a test that it deletes only rows past
the configured age; a restore drill recorded in `docs/runbook.md` with its transcript under
`evidence/`.

## 23.8 Larger data and temporal validation

A newer, larger, locally relevant dataset, and an out-of-time split instead of a random one. Check:
the split is by period, the metrics are reported per period, and the report states the drift it
finds rather than only the aggregate score.

## 23.9 Mobile and accessibility

A responsive review at more widths, a screen-reader pass, and a WCAG 2.1 AA self-assessment. Check:
an accessibility checklist with the observations that support each line, not a claim of conformance.

## Evidence

- `docs/architecture.md`
- `docs/inference_contract.md`
- `docs/deployment.md`
- `evidence/s9/hygiene.txt`
- `docs/acceptance/S13.md`
- `docs/runbook.md`
- `models/metrics.json`
