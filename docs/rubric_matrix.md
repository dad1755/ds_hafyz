# Rubric matrix — every marked item mapped to the sprint that produces its evidence

Two authorities are mapped here: `Group Project 40%.md` (assessment authority) and
`blueprint.md` §9/§10 (sprint plan). Precedence: see `docs/source_of_truth.md`.

Legend — **Status**: `verified` (evidence exists in this repo) · `claimed` (draft
assertion, not reproduced) · `pending` (sprint not run) · `blocked` (needs operator).

As of Sprint 0: only the items marked `verified` below have real evidence. Everything
else is `pending`, and the report may not describe it as done.

---

## 1. Report — 26 mandatory components (20 marks)

Component numbering follows `Group Project 40%.md` §18A exactly; the brief allows
grouping under chapters **only if** all 26 stay findable via headings or this crosswalk.

| # | Required component | Producing sprint | Evidence artifact (path) | Status |
|---:|---|---|---|---|
| 1 | Cover Page | S14 | `docs/report/01_cover.md` | pending |
| 2 | Executive Summary | S14 | `docs/report/02_executive_summary.md` | pending |
| 3 | Introduction | S14 | `docs/report/03_introduction.md` | pending |
| 4 | Problem Statement | S0 → S14 | `docs/report/04_problem_statement.md` (framing frozen in `docs/architecture.md` §1) | pending |
| 5 | Objectives | S0 → S14 | `docs/report/05_objectives.md` (SMART objectives seeded here) | pending |
| 6 | Project Scope | S0 → S14 | `docs/report/06_scope.md` + no-go list in `docs/architecture.md` §8 | pending |
| 7 | Dataset Description | **S0** → S2 → S14 | `evidence/s0/inspect_dataset.txt`, `docs/data_dictionary.md` (S2), `README.md` provenance | **verified** (S0 facts + S2 contract) |
| 8 | Data Preprocessing | S3 → S14 | `ml/preprocess.py` + `docs/report/08_preprocessing.md` | pending |
| 9 | Exploratory Data Analysis | S3 → S14 | `models/eda/*.png` (6 plots) + interpretations in `docs/report_evidence.md` | pending |
| 10 | Machine Learning Methodology | S4 → S14 | `docs/report/10_methodology.md` + `ml/train.py` | pending |
| 11 | Model Training | S4 → S14 | `models/metrics.json` (seeds, hyperparameters, package versions) | pending |
| 12 | Model Evaluation | S4 → S14 | `models/metrics.json`, 3 confusion matrices | pending |
| 13 | Model Comparison | S4 → S14 | `models/metrics.json` comparison table + majority-class baseline | pending |
| 14 | System Architecture and Design | **S0** → S1 → S14 | `docs/architecture.md` (this sprint) + `compose.yaml` (S1) | **verified** (design) |
| 15 | Admin Module | S8 → S9 → S14 | `evidence/screenshots/admin_*.png` from a running stack | pending |
| 16 | User Module | S7 → S14 | `evidence/screenshots/user_*.png` | pending |
| 17 | Predictive Model Integration | S5 → S14 | `models/model_manifest.json`, `ml/verify_artifact.py` output | pending |
| 18 | System Testing | S11 → S14 | `docs/test_matrix.md` with T01–T12 observed results | pending |
| 19 | Results and Discussion | S4/S11 → S14 | `models/metrics.json` + `docs/report/19_results.md` | pending |
| 20 | Ethical and Privacy Considerations | **S0** → S14 | `docs/architecture.md` §7 threat/data-sensitivity model | **verified** (analysis) |
| 21 | Challenges and Solutions | S11 → S14 | `docs/report/21_challenges.md` (logged as they happen) | pending |
| 22 | Limitations | S0 → S4 → S14 | recall ceiling, 2005 Taiwan context, NTD — `docs/report_evidence.md` §5 | pending |
| 23 | Future Enhancements | S14 | `docs/report/23_future_work.md` | pending |
| 24 | Conclusion | S14 | `docs/report/24_conclusion.md` | pending |
| 25 | References | **S0** → S14 | citation block in `README.md` (UCI, Yeh & Lien 2009, scikit-learn, Streamlit) | **verified** (source + citation) |
| 26 | Appendices | S0 → S14 | `evidence/`, `ml/*.py`, dataset schema | pending |

**Count check:** 26 rows. The 26th must not be dropped when chapters are merged.

---

## 2. Rubric A — Project Report (20 marks)

| # | Criterion (brief §Rubric A) | Marks | Evidence required | Sprints | Status |
|---:|---|---:|---|---|---|
| A1 | Problem statement, objectives & scope | 2 | Clear finance problem, measurable objectives, binary scope with explicit non-goals | S0, S14 | pending |
| A2 | Dataset selection, description & preprocessing | 3 | UCI provenance, 25 columns, class distribution, justified cleaning decisions | **S0**, S2–S3 | **partly verified** (provenance + facts) |
| A3 | Exploratory data analysis | 2 | Six real plots, each with a substantive interpretation | S3 | pending |
| A4 | ML methodology & model development | 3 | Features, target, split, seeds, three algorithms, no leakage | S4 | pending |
| A5 | Model testing, evaluation & interpretation | 3 | Held-out accuracy/precision/recall/F1, confusion matrices, critical comparison, baseline | S4–S5 | pending |
| A6 | System design & model integration | 2 | Architecture diagram, RBAC design, artifact → app path | **S0**, S1, S5–S10 | **partly verified** (design) |
| A7 | Results, discussion, challenges & ethics | 2 | Observed results, real obstacles, privacy/bias/limitation analysis | S0, S11, S14 | pending |
| A8 | Conclusion & future enhancements | 1 | Evidence-backed conclusion, realistic roadmap | S14 | pending |
| A9 | Structure, referencing & professional quality | 2 | Consistent figure/table indexes, academic citations, appendix | S0, S14 | pending |
| | **Total** | **20** | | | |

## 3. Rubric B — Presentation & System Demonstration (20 marks)

| # | Criterion (brief §Rubric B) | Marks | Evidence required | Sprints | Status |
|---:|---|---:|---|---|---|
| B1 | Introduction, problem & objectives | 2 | Slide deck opener, rehearsed | S15 | pending |
| B2 | Dataset, preprocessing & EDA explanation | 2 | Real plots + dataset facts explained aloud | S3, S15 | pending |
| B3 | ML methodology & results | 3 | Metrics/confusion matrices explained, selection justified | S4, S10, S15 | pending |
| B4 | Admin module demonstration | 2 | Live user + dataset management, no hard-coded data | S8–S9, S15 | pending |
| B5 | User module & prediction demonstration | 3 | Live 23-field form → class + probability + advice | S5, S7, S15 | pending |
| B6 | Overall system integration & functionality | 3 | Public HTTPS stack, working end-to-end | S11–S13 | pending |
| B7 | Presentation quality & communication | 2 | Rehearsed, timed, consistent visuals | S15 | pending |
| B8 | Team participation & individual understanding | 1 | Real, confirmed member contributions (not invented) | S15 | blocked (needs group confirmation) |
| B9 | Q&A / technical understanding | 2 | Question bank + drill on accuracy-vs-recall, leakage, imbalance, RBAC | S15 | pending |
| | **Total** | **20** | | | |

## 4. Presentation content coverage (brief §18B — 15 topics)

| # | Topic | Covered in | Sprint |
|---:|---|---|---|
| P1 | Problem | deck slide 1 | S15 |
| P2 | Objectives | slide 1 | S15 |
| P3 | Dataset | slide 3 + `docs/report_evidence.md` | S0/S15 |
| P4 | Data preprocessing | slide 4 | S3/S15 |
| P5 | Exploratory analysis | slide 5 (real plots) | S3/S15 |
| P6 | ML methodology | slide 6 | S4/S15 |
| P7 | Model performance | slide 7 (real metrics only) | S4/S15 |
| P8 | System architecture | slide 8 | S0/S15 |
| P9 | Admin module | live demo | S8–S9/S15 |
| P10 | User module | live demo | S7/S15 |
| P11 | Prediction process | live demo | S5/S7/S15 |
| P12 | System results | slide 10 (real test evidence) | S11/S15 |
| P13 | Limitations | slide 11 | S14/S15 |
| P14 | Recommendations | slide 11 | S5/S15 |
| P15 | Future enhancements | slide 12 | S14/S15 |

## 5. Gate checks for this matrix

- [x] All 26 report components listed and each assigned a producing sprint.
- [x] Rubric A: 9 criteria summing to 20 marks.
- [x] Rubric B: 9 criteria summing to 20 marks.
- [x] All 15 presentation topics mapped.
- [ ] Every row `verified` with archived output — **not yet; S0 covers only rows 7, 14, 20, 25.**
- [ ] Zero unverifiable "PASS" statements — enforced from S11 onward.
