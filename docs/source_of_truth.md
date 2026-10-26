# Source of truth and precedence

Frozen in Sprint 0. When two sources disagree, the higher row wins. Nothing in this
file may be overridden by prose in a draft, a chat message or a slide.

| Rank | Source | Path | Role | May it be quoted as evidence? |
|---:|---|---|---|---|
| 1 | Assessment authority | `Group Project 40%.md` | Defines the 26 report components, Rubric A (20 marks), Rubric B (20 marks), required submission and instructions. | Yes — as requirements, never as results. |
| 2 | Implementation specification | `blueprint.md` | Sprint 0–16 roadmap, architecture, security defaults, acceptance commands, release gates. | Yes — as the plan. Deviations must be recorded in `docs/architecture.md`. |
| 3 | Executed, reproducible run output | `evidence/`, `models/metrics.json`, test logs | Actual command output from this repository on this host. | **Yes — the only acceptable form of a result.** |
| 4 | Dataset | `data/UCI_Credit_Card.csv` | The immutable benchmark seed; inspected by code, never edited. | Yes, after `ml/inspect_dataset.py` passes. |
| 5 | Detailed draft | `Credit_Card_Default_Prediction_Project-v3.docx` | Starting design and narrative scaffolding. | No — every number is `claimed` until reproduced. |
| 6 | Earlier draft | `Credit_Card_Default_Prediction_Project.docx` | Context only. | No. |
| 7 | Chat, verbal instruction, presentation notes | — | Intent and operator decisions. | No. Decisions are recorded in this repo or they did not happen. |

## Precedence rules

1. **Assessment beats blueprint.** If the brief demands a component the blueprint does
   not schedule, the brief wins and the gap is logged in `docs/rubric_matrix.md`.
2. **Blueprint beats draft.** Where the draft contradicts the spec (password hashing,
   class wording, hosting status), the spec wins.
3. **Run output beats every claim.** A metric, screenshot, test pass or deployment
   result that was not produced by a command in this repository does not exist.
4. **Code beats prose about the data.** The dataset is described by
   `ml/inspect_dataset.py`, not by the draft's Table 7/Table 8.
5. **The dataset is immutable.** Verification never "fixes" the CSV. A disagreement is
   reported, not repaired.
6. **Sprint 0 modifies no host, DNS, tunnel or container.** The ingress is a given.

## Conflict register (found in Sprint 0, resolved here)

| # | Conflict | Sources | Resolution |
|---:|---|---|---|
| C1 | Class counts and size | draft v3 vs CSV | **CSV confirmed by code:** 30,000 × 25, class 0 = 23,364 (77.88%), class 1 = 6,636 (22.12%). Draft agrees; it was still verified independently. |
| C2 | Password hashing | draft v3 §5.2 "secure SHA256 hashes" vs blueprint §2/§12.2 | **Blueprint wins:** Argon2id or bcrypt via a vetted library. Bare SHA-256 is prohibited; the report text must be corrected in S14. |
| C3 | Target class wording | draft v3 "On Time Class 0" vs blueprint §5.9 | **Blueprint wins:** "Predicted non-default next month" / "Predicted default next month". No certainty implied. |
| C4 | Cloud hosting | draft v3 §1.3 lists "cloud server hosting" as future work vs operator-authorised deployment to `www.aihubcampus.online` | **Deployment is in scope (S13).** Future work is re-scoped to enterprise DB, monitoring, retraining and recall. |
| C5 | Ingress port | blueprint §2/§7 routes the tunnel to `http://web:8501` vs the operator's ingress, which publishes `www.aihubcampus.online` **and** `aihubcampus.online` to `http://web:2026` | **Observed ingress wins:** the app listens on **2026**. Resolution and rationale in `docs/architecture.md` §5. |
| C6 | Repayment status column name | blueprint §4 correctly lists `PAY_0, PAY_2…PAY_6` (no `PAY_1`) vs UCI's own documentation, which calls the second column `PAY_2` | **Dataset wins:** the CSV has `PAY_2` and no `PAY_1`. Six status columns; never invent `PAY_1`. |
| C7 | Education "four main groups" and a 5.7% "others" rate | draft v3 §3.5 vs CSV | **CSV wins:** `EDUCATION` has 7 observed codes (0–6). 5.7% is code 4 alone; the true aggregate of codes 0,4,5,6 is 7.05%. Draft sentence must be rewritten in S14. |
| C8 | Numeric dtype summary | draft v3 Table 7 types vs CSV text | **CSV wins:** 4,262 monetary cells are written in scientific notation (`5e+05`), so a naive integer parse misclassifies 13 columns as float. All values are whole NTD; documented in `docs/report_evidence.md`. |
| C9 | Team size, 14-day schedule, 12 PASS results | draft v3 §1.4, §6.1 vs no evidence | **Unverified.** Not repeatable as fact until the group confirms membership/schedule and T01–T12 are re-executed with recorded output (S11, S14). |
| C10 | Model metrics | draft v3 Table 9 vs no artifact in this repo | **Claimed only.** Must be reproduced in S4 with a recorded split seed and confusion matrices, or the observed values published instead. |
| C11 | Bootstrap admin username | blueprint §6 says `web`; the operator's `.env` sets `INITIAL_ADMIN_USERNAME=ds_hafyz` | **Operator `.env` wins:** the app reads the username from the environment and seeds nothing else. `web` in the blueprint is an example value, not a requirement. |
| C12 | Credentials on disk | operator record `PROJECT_DETAILS.md` contains plaintext demo passwords and was **not** git-ignored | **Now ignored** (`.gitignore`, S0). The file is the operator's record: not deleted, not edited, never committed. Rotation before public sharing remains the operator's action. |

## Status vocabulary

Used in `docs/rubric_matrix.md` and `docs/report_evidence.md`:

- `verified` — produced by a command in this repo, output archived under `evidence/`.
- `claimed` — asserted by a draft or a person, not yet reproduced.
- `pending` — the sprint that produces it has not run.
- `blocked` — cannot be produced without an operator action (credential, DNS, approval).
