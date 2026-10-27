# 13. Model Comparison

Draft, Sprint 14.

## 13.1 Selection, restated as a decision

The rule was fixed before the results were seen: maximise mean five-fold cross-validated F1 on the
default class over the training rows; break ties within 0.005 by recall, then precision; the
held-out rows are not consulted. The ranking it produced:

| Rank | Candidate | CV F1 | CV recall | CV precision |
|---:|---|---:|---:|---:|
| 1 | Decision tree | 0.464273 | 0.351294 | 0.686803 |
| 2 | Random forest | 0.419124 | 0.300060 | 0.695916 |
| 3 | Logistic regression | 0.364699 | 0.245244 | 0.711799 |

The decision tree wins by 0.045 CV F1 over the forest — more than three times the fold standard
deviation — so the choice does not depend on tie-breaking.

## 13.2 What changes if a different rule is used

This is the comparison the report owes the reader, because "we picked the best model" is only
meaningful relative to a criterion:

| If the criterion were… | Winner | Consequence for the system |
|---|---|---|
| Accuracy | Decision tree (0.8172) | Same model, but the margin over the baseline (0.7788) is only 3.8 points and the metric hides the 855 missed defaulters. |
| ROC-AUC | Random forest (0.7665) | Better ranking across thresholds, worse at the deployed 0.5 threshold; would need threshold work the project did not do. |
| Precision | Logistic regression (0.6868) | Fewer false alarms, but catches only 318 of 1,327 defaulters. |
| Recall | Decision tree (0.3557) | Same model as the delivered one — the only case where the "catch defaulters" objective and the delivered rule agree. |
| F1 (the rule used) | Decision tree (0.4625) | Delivered. |

The table is the honest answer to "was the right model chosen?": the decision tree is the right
choice for a system whose purpose is to flag likely defaulters for human follow-up, and it would be
the wrong choice for a system optimised to avoid false alarms.

## 13.3 Against the earlier draft's numbers

The draft this project replaced reported LR 0.8077 / DT 0.8172 / RF 0.8122 accuracy and DT F1
0.4620. Those figures reproduce from the shipped artifact and metrics — LR and RF to four decimals,
DT to ~1e-3; the reproduction is recorded in `docs/report_evidence.md` §7.3, and it is a check
that the delivered pipeline is the pipeline the draft described. What the draft did *not* report is
the recall figure that matters (0.3557) or the baseline that makes accuracy meaningless. The
correction is not to the arithmetic but to the framing.

## 13.4 Why no fourth model

A gradient-boosted model would probably improve F1, and it is the obvious next candidate. It was not
built because the project's constraint was a fixed, explainable, dependency-light stack
(scikit-learn only) and because an improved model would not change the central finding: at a fixed
0.5 threshold on this data, recall for the default class is limited by the features available, not
by the estimator. That claim is a judgement, not a measurement, and it is labelled as one.

## Evidence

- `models/metrics.json`
- `evidence/s4/train.txt`
- `evidence/s4/evaluate.txt`
- `docs/report_evidence.md`
- `docs/acceptance/S04.md`
