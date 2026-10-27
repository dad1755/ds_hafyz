# Rubric matrix — every marked item mapped to the evidence that supports it

Two authorities are mapped here: `Group Project 40%.md` (assessment authority: 26 report
components, rubric A, rubric B, 15 presentation topics) and `blueprint.md` §9/§10 (sprint plan).
Precedence when they disagree: `docs/source_of_truth.md`.

**Status vocabulary**, used in every table below:

| Status | Meaning |
|---|---|
| `evidenced` | The artefact exists in this repository and a recorded command produced it. The path is given. |
| `draft` | The report text exists at the given path and cites evidence, but the text itself has not passed an independent gate (S14 is the current draft; its gate is a different agent). |
| `unconfirmed` | The fact belongs to the group and no record here supports it. It is not asserted anywhere. |
| `pending` | A later sprint produces it (S15 presentation, S16 final packaging). |
| `missing` | The report needs it and the project does not have it. Named, not filled. |

As of Sprint 14: the 26 components all have drafts; the evidence behind them is recorded; the
draft text awaits its gate. Nothing in this file claims a gate verdict it did not receive.

---

## 1. Report — 26 mandatory components (20 marks)

Numbering follows `Group Project 40%.md` §18A exactly. The brief allows grouping under chapters
**only if** all 26 stay findable through headings or this crosswalk; each row therefore names the
draft file whose heading carries the component.

| # | Required component | Draft file | Evidence behind it (path) | Status |
|---:|---|---|---|---|
| 1 | Cover Page | `docs/report/01_cover.md` | group facts (members, IDs, date) — **not recorded anywhere in this repo** | `draft`; member/date fields `unconfirmed` |
| 2 | Executive Summary | `docs/report/02_executive_summary.md` | `models/metrics.json`, `docs/test_matrix.md`, `evidence/s13/browser_check.txt` | `draft` |
| 3 | Introduction | `docs/report/03_introduction.md` | `docs/architecture.md`, `docs/inference_contract.md` | `draft` |
| 4 | Problem Statement | `docs/report/04_problem_statement.md` | `models/eda/summary.json` (77.88 / 22.12), `docs/data_dictionary.md` | `draft` |
| 5 | Objectives | `docs/report/05_objectives.md` | O1–O15 each name its check; O13 (recall > 0.60) recorded as **not met** | `draft`; O15 `unconfirmed` |
| 6 | Project Scope | `docs/report/06_scope.md` | `docs/architecture.md` §8 no-go list | `draft` |
| 7 | Dataset Description | `docs/report/07_dataset_description.md` | `evidence/s0/inspect_dataset.txt` (30,000 × 25, 0 missing, SHA-256), `docs/data_dictionary.md` | `evidenced` + `draft` |
| 8 | Data Preprocessing | `docs/report/08_preprocessing.md` | `docs/preprocessing_contract.md`, leakage check in `models/metrics.json` | `evidenced` + `draft` |
| 9 | Exploratory Data Analysis | `docs/report/09_eda.md` | six figures `models/eda/01…06*.png`, `models/eda/summary.json`, `evidence/s3/eda_run.txt` | `evidenced` + `draft` |
| 10 | Machine Learning Methodology | `docs/report/10_methodology.md` | `docs/preprocessing_contract.md`, `ml/train.py`, `models/metrics.json` `selection.rule` | `evidenced` + `draft` |
| 11 | Model Training | `docs/report/11_training.md` | `evidence/s4/train.txt`, `models/metrics.json` (CV table, hyperparameters, versions) | `evidenced` + `draft` |
| 12 | Model Evaluation | `docs/report/12_evaluation.md` | `evidence/s4/evaluate.txt`, three confusion-matrix figures, arithmetic check | `evidenced` + `draft` |
| 13 | Model Comparison | `docs/report/13_comparison.md` | `models/metrics.json` ranking + baseline row; criterion-sensitivity table | `evidenced` + `draft` |
| 14 | System Architecture and Design | `docs/report/14_architecture.md` | `docs/architecture.md`, `compose.yaml`, `Dockerfile`, `evidence/s12/smoke_test.txt` | `evidenced` + `draft` |
| 15 | Admin Module | `docs/report/15_admin_module.md` | `evidence/s8/` (list/create/edit/reset/deactivate, audit probe), `evidence/s9/` (dataset manager) | `evidenced` + `draft` |
| 16 | User Module | `docs/report/16_user_module.md` | `evidence/s7/ui_vs_pipeline.txt`, 375 px screenshots, `evidence/s13/tunnel_user_prediction.png` | `evidenced` + `draft` |
| 17 | Predictive Model Integration | `docs/report/17_model_integration.md` | `docs/inference_contract.md`, `evidence/s5/verify_artifact.txt`, `evidence/s5/tamper.txt`, `evidence/s11/restart.txt` | `evidenced` + `draft` |
| 18 | System Testing | `docs/report/18_system_testing.md` | `docs/test_matrix.md` T01–T12, `evidence/s11/test-results/pytest_all_verbose.txt` (285 passed), `t_matrix_extract.txt` | `evidenced` + `draft` |
| 19 | Results and Discussion | `docs/report/19_results_discussion.md` | `models/metrics.json`, correction table (E1–E7) against `docs/report_evidence.md` §17 | `evidenced` + `draft` |
| 20 | Ethical and Privacy Considerations | `docs/report/20_ethics_privacy.md` | `docs/architecture.md` §7 threat model, `evidence/s11/probe_http.txt`, `evidence/s13/check_no_secrets.txt` | `evidenced` + `draft` |
| 21 | Challenges and Solutions | `docs/report/21_challenges.md` | C1–C10 each cite the file where the obstacle and its fix are recorded; group plan `unconfirmed` | `draft`; group plan `unconfirmed` |
| 22 | Limitations | `docs/report/22_limitations.md` | recall 0.3557 / 855 missed (`models/metrics.json`), F-1–F-3 (`docs/deployment.md` §10.5) | `evidenced` + `draft` |
| 23 | Future Enhancements | `docs/report/23_future_enhancements.md` | each item names its check; none claimed as done | `draft` |
| 24 | Conclusion | `docs/report/24_conclusion.md` | restates measured numbers only | `draft` |
| 25 | References | `docs/report/25_references.md` | UCI DOI, Yeh & Lien 2009, library citations, internal documents | `evidenced` + `draft` |
| 26 | Appendices | `docs/report/26_appendices.md` | schema (`ml/schema.py`), config names only (`.env.example`), commands, code map, acceptance history | `evidenced` + `draft` |

**Count check:** 26 rows, each naming a file that exists. The 26th must not be dropped when
chapters are merged.

Supporting deliverable for this rubric: `docs/report/00_figure_table_inventory.md` — 29 figures
(F1–F28 real files, F29 marked `missing` as a rendered diagram) and 23 tables (T1–T23), each with
its caption numbers and the file they come from.

---

## 2. Rubric A — Project Report (20 marks)

| # | Criterion (brief §Rubric A) | Marks | Evidence in this repo | Status |
|---:|---|---:|---|---|
| A1 | Problem statement, objectives & scope | 2 | `docs/report/04_problem_statement.md`, `05_objectives.md` (15 checkable objectives incl. two recorded as not met), `06_scope.md` | `draft` |
| A2 | Dataset selection, description & preprocessing | 3 | `evidence/s0/inspect_dataset.txt`, `docs/data_dictionary.md`, `docs/preprocessing_contract.md`, `07`–`08` | `evidenced` + `draft` |
| A3 | Exploratory data analysis | 2 | six regenerated figures, `models/eda/summary.json`, captions with numbers in `09_eda.md` | `evidenced` + `draft` |
| A4 | ML methodology & model development | 3 | `models/metrics.json` (split, seeds, three pipelines, scaler-on-train leak check), `evidence/s4/train.txt` | `evidenced` + `draft` |
| A5 | Model testing, evaluation & interpretation | 3 | held-out metrics, three confusion matrices, baseline row, arithmetic check, criterion-sensitivity table (`12`–`13`) | `evidenced` + `draft` |
| A6 | System design & model integration | 2 | `docs/architecture.md`, `docs/inference_contract.md`, `evidence/s5/verify_artifact.txt`, `evidence/s12/smoke_test.txt` | `evidenced` + `draft` |
| A7 | Results, discussion, challenges & ethics | 2 | `19`–`21`, correction table E1–E7, threat model, fairness gap stated | `evidenced` + `draft` |
| A8 | Conclusion & future enhancements | 1 | `24_conclusion.md`, `23_future_enhancements.md` | `draft` |
| A9 | Structure, referencing & professional quality | 2 | `00_figure_table_inventory.md`, `25_references.md`, 26 numbered files, one numbering scheme | `draft` |
| | **Total** | **20** | | |

## 3. Rubric B — Presentation & System Demonstration (20 marks)

| # | Criterion (brief §Rubric B) | Marks | Evidence / where it will come from | Status |
|---:|---|---:|---|---|
| B1 | Introduction, problem & objectives | 2 | `docs/report/03_introduction.md`, `04_problem_statement.md`, `05_objectives.md` supply the content; the deck is S15 | `pending` (content `draft`) |
| B2 | Dataset, preprocessing & EDA explanation | 2 | `07`–`09` + six real figures | `pending` (content `draft`) |
| B3 | ML methodology & results | 3 | `10`–`13` + `evidence/s10/evaluation_375px_top.png` (live panel) | `pending` (content `draft`) |
| B4 | Admin module demonstration | 2 | live: user management + dataset staging, `evidence/s9/probe_datasets.txt` | `evidenced` (system), `pending` (rehearsal) |
| B5 | User module & prediction demonstration | 3 | live 23-field form → class + probability + advice, `evidence/s7/ui_vs_pipeline.txt` | `evidenced` (system), `pending` (rehearsal) |
| B6 | Overall system integration & functionality | 3 | public HTTPS end-to-end: `evidence/s13/browser_check.txt` (29 checks), `evidence/s13/smoke_test.txt` (16/16) | `evidenced` |
| B7 | Presentation quality & communication | 2 | deck, timing, visuals — S15 | `pending` |
| B8 | Team participation & individual understanding | 1 | **requires the group**: who did what, confirmed by the members. No record exists in this repo | `unconfirmed` |
| B9 | Q&A / technical understanding | 2 | question bank to be built from `19`–`23` and `docs/test_matrix.md` | `pending` |
| | **Total** | **20** | | |

B8 is the one item this repository cannot produce. Any name or split written into the report
without the group's confirmation would be a fabrication, so the row stays `unconfirmed` and the
cover page carries explicit placeholders.

## 4. Presentation content coverage (brief §18B — 15 topics)

| # | Topic | Source the deck must draw on | Status |
|---:|---|---|---|
| P1 | Problem | `docs/report/04_problem_statement.md` | `draft` |
| P2 | Objectives | `docs/report/05_objectives.md` | `draft` |
| P3 | Dataset | `docs/report/07_dataset_description.md`, `evidence/s0/inspect_dataset.txt` | `evidenced` |
| P4 | Data preprocessing | `docs/report/08_preprocessing.md` | `evidenced` |
| P5 | Exploratory analysis | `docs/report/09_eda.md`, six figures | `evidenced` |
| P6 | ML methodology | `docs/report/10_methodology.md` | `evidenced` |
| P7 | Model performance | `docs/report/12_evaluation.md`, `models/metrics.json` | `evidenced` |
| P8 | System architecture | `docs/report/14_architecture.md`, `docs/architecture.md` §2 | `evidenced` |
| P9 | Admin module | live system, `evidence/s8/`, `evidence/s9/` | `evidenced` |
| P10 | User module | live system, `evidence/s7/` | `evidenced` |
| P11 | Prediction process | `docs/report/17_model_integration.md`, live form | `evidenced` |
| P12 | System results | `docs/report/18_system_testing.md`, `docs/test_matrix.md` | `evidenced` |
| P13 | Limitations | `docs/report/22_limitations.md` | `draft` |
| P14 | Recommendations | `docs/report/16_user_module.md` §16.3 (band advice), `19` §19.4 | `draft` |
| P15 | Future enhancements | `docs/report/23_future_enhancements.md` | `draft` |

## 5. Gate checks for this matrix

Mechanical checks, run by `evidence/s14/check_report_refs.py`; its output is committed at
`evidence/s14/check_report_refs.txt`.

- [x] All 26 report components listed, each with a draft file that exists.
- [x] Rubric A: 9 criteria summing to 20 marks.
- [x] Rubric B: 9 criteria summing to 20 marks.
- [x] All 15 presentation topics mapped to a source.
- [x] Every path cited in `docs/report/*.md`, this file and `docs/report_evidence.md` exists on disk.
- [x] Every number in a figure or table caption traces to a file named beside it.
- [x] No line in the drafts claims PASS/completed/live without a cited evidence path.
- [x] Group-owned facts (members, IDs, dates, contribution split, fourteen-day schedule) are
      marked `unconfirmed`; none is stated as fact.
- [ ] Every draft read by a human editor for prose quality — **not done; the S14 gate is the next
      step, and this file does not certify it.**

## 6. What is still missing, stated plainly

| Item | Why it is missing | Who can supply it |
|---|---|---|
| Cover-page member names, student IDs, course code, lecturer, submission date | Not recorded anywhere in this repository; inventing them would be a fabrication | The group |
| Contribution split (B8) | Only the members know it; the earlier draft's version is unconfirmed | The group |
| A rendered architecture diagram (F29) | The source is Mermaid in `docs/architecture.md` §2; rendering is a formatting task | S15 |
| Slide deck, script, Q&A bank (B1, B7, B9) | S15 deliverable | S15 |
| Fairness audit | Not attempted; named as future work (§23.3) | Post-project |
| Retention policy decision | Operator decision, still open (`docs/architecture.md` §10) | Operator |
