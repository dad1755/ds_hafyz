# 12. Model Evaluation

Draft, Sprint 14. Every number below is read from `models/metrics.json`; the verbatim run output is
`evidence/s4/evaluate.txt`, and the figures are the four PNGs under `models/figures/`.

## 12.1 The held-out comparison

6,000 rows scored once, at threshold 0.5, positive class = default:

| Model | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---:|---:|---:|---:|---:|
| Always class 0 (baseline) | 0.7788 | 0.0000 | 0.0000 | 0.0000 | — |
| Logistic regression | 0.8077 | 0.6868 | 0.2396 | 0.3553 | 0.7076 |
| Decision tree (**selected**) | **0.8172** | 0.6611 | **0.3557** | **0.4625** | 0.7423 |
| Random forest | 0.8122 | 0.6773 | 0.2879 | 0.4040 | **0.7665** |

The baseline row is the point of the table. It reaches 0.7788 accuracy — exactly the class-0 share —
with zero recall and zero F1. Any model that reports accuracy without that row is inviting a
misreading, which is why the baseline is rendered beside every model in the admin panel too.

## 12.2 The confusion matrices

Each model's 2×2 over the same 6,000 rows:

| Model | TN | FP | FN | TP |
|---|---:|---:|---:|---:|
| Logistic regression | 4,528 | 145 | 1,009 | 318 |
| Decision tree | 4,431 | 242 | 855 | 472 |
| Random forest | 4,491 | 182 | 945 | 382 |

The selected model misses **855 of the 1,327 accounts that defaulted** — 64.4% of defaulters. It
also flags 242 accounts that did not default. Every metric in §12.1 can be recomputed from these
four numbers, and the arithmetic is checked: `max_abs_delta` between the reported metrics and the
metrics derived from TN/FP/FN/TP is 0.0 for all three models.

## 12.3 The three candidates, read honestly

- **Decision tree.** Best F1 and best recall of the three, at the cost of the lowest precision
  (0.6611). It is the selected model because the selection rule was fixed in advance and it wins on
  that rule. Its depth of 5 keeps it shallow enough to describe, which is a real advantage for a
  system whose output a human is meant to interpret.
- **Logistic regression.** Highest precision (0.6868) and the worst recall (0.2396): it is the most
  conservative model, and at this threshold it catches fewer than a quarter of defaulters.
- **Random forest.** Best ROC-AUC (0.7665) but middling F1 at 0.5. Its ranking quality is real; the
  fixed threshold is what costs it. This is the clearest example in the project of why "best AUC"
  and "best system" are different questions.

## 12.4 What the model is actually using

Impurity-based importances from the deployed tree: `PAY_0` 68.01%, `PAY_2` 13.77%, `PAY_AMT3`
4.40%, `PAY_5` 3.31%, `BILL_AMT1` 3.17%, `LIMIT_BAL` 2.19%, and the remaining 17 features sharing
about 5%. The model is largely a recoding of recent repayment status. That is defensible — it
matches the EDA (§9.2d) and it is what a credit reviewer looks at first — but it means the
project's contribution is the system and the evaluation discipline, not a novel predictive
insight. Saying so is more useful than claiming otherwise.

## 12.5 What the evaluation does not establish

- **Calibration.** The probability is uncalibrated: no reliability curve, no Brier score, no
  Platt/isotonic step. The UI therefore labels the number "estimated, uncalibrated" and the report
  does not call it a probability of default in the actuarial sense.
- **Stability over time.** One split, one seed. There is no temporal validation and no
  out-of-time test, so nothing here says the model would hold on 2006 data, let alone 2026 data.
- **Fairness.** No subgroup metrics were computed (§20.3, §22.4).
- **Cost-weighted performance.** No cost matrix exists, so the 0.5 threshold is a stated choice,
  not an optimum.

## Evidence

- `models/metrics.json`
- `models/figures/confusion_logistic_regression.png`
- `models/figures/confusion_decision_tree.png`
- `models/figures/confusion_random_forest.png`
- `models/figures/feature_importance_selected.png`
- `evidence/s4/evaluate.txt`
- `evidence/s4/feature_importances.txt`
- `evidence/s10/trace_metrics.txt`
