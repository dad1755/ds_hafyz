# 19. Results and Discussion

Draft, Sprint 14.

## 19.1 The result, stated plainly

The delivered system predicts next-month default from 23 features with held-out accuracy 0.8172,
precision 0.6611, recall 0.3557, F1 0.4625 and ROC-AUC 0.7423. It beats the constant-answer
baseline by 0.0383 accuracy, 0.4625 F1 and 0.3557 recall, and it misses 855 of the 1,327 accounts
that defaulted.

The interesting question is not whether that beats the baseline — it does, on the metrics that
matter — but whether it is good enough for the use the interface implies. For a "flag this account
for a supportive conversation" use, a model that catches about a third of defaulters while
mis-flagging about one in six non-defaulters is weak but not useless: it concentrates human
attention on 714 accounts (472 true positives + 242 false positives) out of 6,000, of which 66% are
real defaulters. For an automated decision it is nowhere near sufficient, which is why the system
does not automate one.

## 19.2 Corrections to the earlier draft, and why they matter

The report this project replaces (v3) was written before the system existed. Where its claims could
be recomputed, they were; the full checklist is `docs/report_evidence.md` §17. The corrections that
change meaning rather than wording:

| # | Draft said | Reality | Where it is corrected |
|---|---|---|---|
| E5 | Passwords hashed with SHA-256 | Argon2id (`m=65536, t=3, p=4`), constant-time verify; there is no SHA-256 password path | §14.4, `docs/architecture.md` §9 D2 |
| E6 | Cloud hosting listed as future work | The system is deployed at `https://www.aihubcampus.online` through the operator's tunnel and was verified there | §6, §14.1, `docs/deployment.md` §10 |
| E7 | Class 0 labelled "On Time" | "Predicted non-default next month" — a prediction, not a fact about the account | §16.3, `docs/inference_contract.md` |
| E1 | A clean all-integer dtype table | 4,262 monetary cells arrive in scientific notation; they parse to whole NTD values | §7.4 |
| E2 | Education "others" default rate 5.7% | 5.69% is code 4 alone (n = 123); the four small codes together are 7.05% (n = 468) | §9.2(e) |
| E3 | "Four main education groups" | Seven observed codes (0–6), two of them undocumented by UCI | §9.2(e), §8.4 |
| E4 | Implied `PAY_1` column | There is no `PAY_1`; the columns are `PAY_0, PAY_2…PAY_6` | §7.3 |
| — | "All 12 system tests pass" with no output | 285 cases with a verbatim transcript and a machine check of the cited ids | §18 |
| — | A fourteen-day schedule and a four-member division of work | Neither is recorded or confirmed by the group; both are marked unconfirmed rather than asserted | §21.3, `docs/rubric_matrix.md` B8 |

The last row is the one to be careful about: the schedule and the contribution split may well be
true. They are simply not facts this repository can support, so the report does not state them as
fact.

## 19.3 What the results do not show

- **No claim of generalisation.** One split, one seed, one population. No temporal or out-of-time
  validation was run.
- **No claim of calibration.** The probability is a model score; the UI says so.
- **No claim of fairness.** No subgroup analysis was performed (§20.3).
- **No claim about the deployed system's capacity.** It is a single instance with no load test.
- **No claim that the three-model comparison is exhaustive.** Three sensible defaults, no
  hyperparameter search, no gradient boosting (§13.4).

## 19.4 Discussion: what the project actually demonstrates

Three things, in order of how well they are supported:

1. **A complete, reproducible path from public data to a public system.** The chain validation →
   EDA → split → training → selection → artifact verification → inference → UI → deployment is
   exercised end to end, and each link has a transcript. This is the project's strongest claim.
2. **Evaluation discipline on imbalanced data.** The baseline row, the fixed selection rule, the
   untouched test set, the arithmetic check and the honest recall figure together demonstrate a
   method, not just a result.
3. **A predictive gain that is real but modest.** The tree beats the baseline on F1 and recall; it
   does not become a good default detector, and the report does not pretend otherwise.

## Evidence

- `models/metrics.json`
- `docs/report_evidence.md`
- `docs/test_matrix.md`
- `evidence/s11/test-results/pytest_all_verbose.txt`
- `evidence/s13/browser_check.txt`
- `docs/deployment.md`
- `docs/inference_contract.md`
- `docs/architecture.md`
- `docs/rubric_matrix.md`
