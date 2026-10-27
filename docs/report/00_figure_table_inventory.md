# Figure and table inventory

Every figure and table the report may use, with the file that produces it and the numbers its
caption must quote. A caption may not state a number this inventory does not trace to a file.

Status: draft, Sprint 14. Rows marked **MISSING** are things the report needs and the project
does not have; they are named here rather than filled with something plausible.

## Figures

| ID | Caption (quote these numbers) | File | Produced by |
|---|---|---|---|
| F1 | Distribution of the target: 23,364 accounts did not default next month (77.88%), 6,636 did (22.12%); n = 30,000. | `models/eda/01_target_class_distribution.png` | `ml/generate_eda.py` |
| F2 | Age by outcome class: mean 35.42 years for class 0, 35.73 for class 1 — a difference of 0.31 years, too small to separate the classes. | `models/eda/02_age_by_class.png` | `ml/generate_eda.py` |
| F3 | Credit limit by outcome class: median 150,000 NTD (class 0) against 90,000 NTD (class 1); mean 178,099.73 against 130,109.66 NTD. | `models/eda/03_limit_bal_by_class.png` | `ml/generate_eda.py` |
| F4 | Default rate by `PAY_0` repayment status: 12.81% at code 0 (n = 14,737) rising to 69.14% at code 2 (n = 2,667) and 75.78% at code 3 (n = 322). | `models/eda/04_default_rate_by_pay0.png` | `ml/generate_eda.py` |
| F5 | Default rate by `EDUCATION` code: 19.23% (code 1, n = 10,585), 23.73% (code 2, n = 14,030), 25.16% (code 3, n = 4,917); codes 0, 4, 5 and 6 together are 7.05% (n = 468). | `models/eda/05_default_rate_by_education.png` | `ml/generate_eda.py` |
| F6 | Correlation heatmap of the 13 amount columns; strongest pair `BILL_AMT1`–`BILL_AMT2` r = 0.9515, then `BILL_AMT5`–`BILL_AMT6` r = 0.9462. | `models/eda/06_correlation_heatmap.png` | `ml/generate_eda.py` |
| F7 | Confusion matrix, logistic regression, 6,000 held-out rows: TN 4,528, FP 145, FN 1,009, TP 318. | `models/figures/confusion_logistic_regression.png` | `ml/evaluate.py` |
| F8 | Confusion matrix, decision tree (selected), 6,000 held-out rows: TN 4,431, FP 242, FN 855, TP 472. | `models/figures/confusion_decision_tree.png` | `ml/evaluate.py` |
| F9 | Confusion matrix, random forest, 6,000 held-out rows: TN 4,491, FP 182, FN 945, TP 382. | `models/figures/confusion_random_forest.png` | `ml/evaluate.py` |
| F10 | Impurity-based feature importance of the deployed tree: `PAY_0` 68.01%, `PAY_2` 13.77%, the remaining 21 features share 18.22%. | `models/figures/feature_importance_selected.png` | `ml/evaluate.py` |
| F11 | User prediction form at 375 px: all 23 inputs in four groups, no horizontal overflow. | `evidence/s7/form_375px.png` | `evidence/s7/ui_screenshots.js` |
| F12 | Prediction result panel at 375 px: class, probability to two decimals, band, advice, threshold, model version, disclosures. | `evidence/s7/result_375px.png` | `evidence/s7/ui_screenshots.js` |
| F13 | The account's own prediction history at 375 px. | `evidence/s7/history_375px.png` | `evidence/s7/ui_screenshots.js` |
| F14 | Administrator user management page at 375 px: account list, create form, audit panel. | `evidence/s8/admin_375px.png` | `evidence/s8/ui_screenshots_admin.js` |
| F15 | A new account created through the form, then signed in as. | `evidence/s8/created_375px.png` | `evidence/s8/ui_screenshots_admin.js` |
| F16 | Dataset manager: the deployed model dataset beside the active dataset version. | `evidence/s9/dataset_375px_initial.png` | `evidence/s9/ui_datasets.js` |
| F17 | A 500-row CSV staged as version 2, explicitly not activated. | `evidence/s9/dataset_375px_staged.png` | `evidence/s9/ui_datasets.js` |
| F18 | A malformed upload refused with its recorded reason. | `evidence/s9/dataset_375px_rejected.png` | `evidence/s9/ui_datasets.js` |
| F19 | Model evaluation panel: three candidates, their baseline and the selection rule. | `evidence/s10/evaluation_375px_top.png` | `evidence/s10/ui_evaluation.js` |
| F20 | Model evaluation panel: confusion matrices with TN/FP/FN/TP and their shares. | `evidence/s10/evaluation_375px_confusion.png` | `evidence/s10/ui_evaluation.js` |
| F21 | Model evaluation panel: metadata, artifact digest and the low-recall limitation. | `evidence/s10/evaluation_375px_metadata.png` | `evidence/s10/ui_evaluation.js` |
| F22 | The same evaluation panel at desktop width. | `evidence/s10/evaluation_desktop_top.png` | `evidence/s10/ui_evaluation.js` |
| F23 | The user's navigation contains no administrator section. | `evidence/s10/evaluation_user_nav.png` | `evidence/s10/ui_evaluation.js` |
| F24 | Sign-in through the public hostname. | `evidence/s13/tunnel_signin.png` | `evidence/s13/ui_tunnel.js` |
| F25 | Administrator home through the Cloudflare tunnel, six sections. | `evidence/s13/tunnel_admin_home.png` | `evidence/s13/ui_tunnel.js` |
| F26 | A prediction scored through the public hostname: probability 71.95%, band High. | `evidence/s13/tunnel_user_prediction.png` | `evidence/s13/ui_tunnel.js` |
| F27 | Dataset staged through the public hostname, not activated. | `evidence/s13/tunnel_dataset_staged.png` | `evidence/s13/ui_tunnel.js` |
| F28 | The operator account's forced password-change screen. | `evidence/s13/tunnel_operator_forced_change.png` | `evidence/s13/ui_tunnel.js` |
| F29 | Deployment topology: browser → Cloudflare edge → tunnel → `cloudflared` → `web:2026`, no published port. | **MISSING as a rendered figure** — the diagram exists only as Mermaid source in `docs/architecture.md` §2 | — |

The architecture diagram (F29) is drawn in `docs/architecture.md` §2 as Mermaid plus a plain-text
fallback. Rendering it into the submission format is a formatting task for S15; the source is
real and the inventory records it as a diagram, not a screenshot.

## Tables

| ID | Caption | Source of the numbers |
|---|---|---|
| T1 | Dataset identity: 30,000 rows × 25 columns, 23 predictors, 0 missing cells, 0 duplicate rows, SHA-256 `a0f0ab49…176ca1`. | `evidence/s0/inspect_dataset.txt` |
| T2 | Class distribution: 23,364 (77.88%) / 6,636 (22.12%). | `models/eda/summary.json` |
| T3 | Descriptive statistics for `LIMIT_BAL`, `AGE`, `PAY_0`, `BILL_AMT1` and `PAY_AMT1`. | `models/eda/summary.json` |
| T4 | Default rate by `PAY_0` code, 11 rows. | `models/eda/summary.json` |
| T5 | Default rate by `EDUCATION` code, 7 rows plus the "others" aggregate. | `models/eda/summary.json` |
| T6 | The 25-column contract with units, months and validation rules. | `docs/data_dictionary.md` |
| T7 | Split: 24,000 train / 6,000 test, stratified, `random_state=42`, test class counts 4,673 / 1,327. | `models/metrics.json` |
| T8 | Hyperparameters for the three candidates. | `models/metrics.json` |
| T9 | Five-fold cross-validated F1 / precision / recall / AUC with standard deviations, training rows only. | `models/metrics.json` |
| T10 | Held-out comparison: accuracy, precision, recall, F1, ROC-AUC for the three candidates and the always-class-0 baseline. | `models/metrics.json` |
| T11 | Confusion matrices, three candidates plus the baseline, 6,000 rows. | `models/metrics.json` |
| T12 | Selection ranking by mean cross-validated F1. | `models/metrics.json` |
| T13 | Feature importances, 23 rows. | `evidence/s4/feature_importances.txt` |
| T14 | Risk bands and their advice text. | `docs/inference_contract.md` §4 |
| T15 | The 11 artifact verification checks. | `docs/inference_contract.md` §2 |
| T16 | T01–T12 expected vs observed. | `docs/test_matrix.md` |
| T17 | Adversarial checks: RBAC sweep, upload size boundary, quarantine, secret scan, HTTP probes, log scan, XSRF/CORS. | `docs/test_matrix.md` |
| T18 | Threat model, T1–T12 with control and residual risk. | `docs/architecture.md` §7 |
| T19 | Scope exclusions (the binding no-go list). | `docs/architecture.md` §8 |
| T20 | Deviations from the blueprint, D1–D14, each with its reason. | `docs/architecture.md` §9 |
| T21 | Sprint acceptance history: which sprints have an independent gate record and its verdict. | `docs/acceptance/S00.md` … `docs/acceptance/S13.md` |
| T22 | Findings recorded and not fixed: F-1 hard refresh signs the user out, F-2 the XSRF cookie is not `Secure`, F-3 `http://` does not redirect. | `docs/deployment.md` §10.5 |
| T23 | Rubric crosswalk: 26 report components and 18 marked criteria. | `docs/rubric_matrix.md` |

## Screenshot sets not used

`evidence/s7/home_375px.png`, `home_desktop.png`, `form_filled_375px.png`,
`form_filled_desktop.png`, `evidence/s8/home_375px.png`, `home_desktop.png`,
`new_user_375px.png`, `new_user_desktop.png`, `admin_desktop.png`, `created_desktop.png`,
`evidence/s9/dataset_375px_activated.png`, `evidence/s9/dataset_desktop_initial.png`,
`evidence/s10/evaluation_desktop_confusion.png`, `evaluation_desktop_metadata.png`,
`evidence/s13/tunnel_evaluation.png`, `tunnel_user_home.png`, `tunnel_dataset_staged.png`
(duplicate frame) and `tunnel_prediction_result.png` are committed and available; they are not
in the inventory because the report does not need a second frame of the same page. Selecting
from this list is a formatting choice for S15, not new evidence.

## Evidence

- `models/eda/01_target_class_distribution.png`
- `models/eda/02_age_by_class.png`
- `models/eda/03_limit_bal_by_class.png`
- `models/eda/04_default_rate_by_pay0.png`
- `models/eda/05_default_rate_by_education.png`
- `models/eda/06_correlation_heatmap.png`
- `models/eda/summary.json`
- `models/figures/confusion_logistic_regression.png`
- `models/figures/confusion_decision_tree.png`
- `models/figures/confusion_random_forest.png`
- `models/figures/feature_importance_selected.png`
- `models/metrics.json`
- `docs/architecture.md`
- `docs/data_dictionary.md`
- `docs/inference_contract.md`
- `docs/test_matrix.md`
- `docs/deployment.md`
- `docs/rubric_matrix.md`
- `evidence/s0/inspect_dataset.txt`
- `evidence/s4/feature_importances.txt`
- `evidence/s7/form_375px.png`
- `evidence/s7/result_375px.png`
- `evidence/s7/history_375px.png`
- `evidence/s7/ui_screenshots.js`
- `evidence/s8/admin_375px.png`
- `evidence/s8/created_375px.png`
- `evidence/s8/ui_screenshots_admin.js`
- `evidence/s9/dataset_375px_initial.png`
- `evidence/s9/dataset_375px_staged.png`
- `evidence/s9/dataset_375px_rejected.png`
- `evidence/s9/ui_datasets.js`
- `evidence/s10/evaluation_375px_top.png`
- `evidence/s10/evaluation_375px_confusion.png`
- `evidence/s10/evaluation_375px_metadata.png`
- `evidence/s10/evaluation_desktop_top.png`
- `evidence/s10/evaluation_user_nav.png`
- `evidence/s10/ui_evaluation.js`
- `evidence/s13/tunnel_signin.png`
- `evidence/s13/tunnel_admin_home.png`
- `evidence/s13/tunnel_user_prediction.png`
- `evidence/s13/tunnel_dataset_staged.png`
- `evidence/s13/tunnel_operator_forced_change.png`
- `evidence/s13/ui_tunnel.js`
