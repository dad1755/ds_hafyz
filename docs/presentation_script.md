# 15. Presentation script, live demo and Q&A bank

Sprint 15. Three things a group can present from: a twelve-slide outline whose every number is
the number the artefact records, a demo script that was walked end to end against
`https://www.aihubcampus.online` and whose expected results are the results that rehearsal
produced, and a Q&A bank with answers that survive a technical examiner.

Everything numeric here comes from `models/metrics.json`, `models/eda/summary.json` or the
rehearsal transcript `evidence/s15/demo_rehearsal.txt`. `evidence/s15/check_script_numbers.py`
re-derives the figures from those files and fails if any of them is not in this document, so a
figure typed from memory cannot survive a commit.

## 15.1 Timing — a planning assumption, not an assessment limit

The blueprint records that ten minutes was **v3's draft proposal, not a confirmed assessment
limit**; the lecturer's actual instruction governs. The split below is therefore a plan that fits
in ten minutes and can be stretched or cut, not a claim about the real slot.

| Block | Planned | Measured in rehearsal |
|---|---:|---:|
| Twelve slides | 5 min 30 s | not measured (no rehearsal of the speaking) |
| Live demo, twelve steps | 4 min 0 s | 1 min 37 s of on-screen time (96.7 s total, including tool waits) |
| Close | 30 s | not measured |

The measured figure is the browser's own timing of each demo step, not a human at a keyboard: a
person speaking while clicking is slower, which is why the plan keeps a buffer.

## 15.2 The deck — twelve slides

One slide per row. "On screen" is what the slide carries; "say" is the speaker note.

### Slide 1 — The problem

- **On screen:** a bank must decide, before the statement is due, which accounts are likely to
  miss the next payment; a missed payment is expensive to chase late and cheap to support early.
  Objective: a working web system that scores one account from 23 historical attributes and
  shows the probability **and** what it means, with an honest account of its limits.
- **Say:** we did not set out to beat the state of the art on a 2005 dataset; we set out to build
  a system whose numbers a reader can check.

### Slide 2 — Objectives and scope

- **On screen:** four objectives — (1) a reproducible model from a documented contract,
  (2) a deployed system with two roles, (3) an evaluation an examiner can re-run, (4) stated
  limits. Out of scope by design: no real credit decision, no customer data, no retraining on a
  prediction request.
- **Say:** the scope statement is what stops the ethics question from being an afterthought.

### Slide 3 — The dataset

- **On screen:** UCI *Default of Credit Card Clients* (dataset 350): **30,000** accounts,
  **25** columns, **23** features after dropping `ID` and the target. Target: default next month.
  Class mix **23,364 (77.88%)** no default, **6,636 (22.12%)** default. Seed SHA-256
  `a0f0ab49d6326671d6cd83be5c88dcf18007025fe9a53ecd699119c871176ca1`.
- **Say:** the class mix is the single most important fact on this slide; slide 7 shows why.

### Slide 4 — Preprocessing and the data contract

- **On screen:** the 25 columns in documented order, each with a type, a unit and a legal code
  set; whole-number validation for every field; the same contract used by training, by the
  upload validator and by the prediction form. Codes are kept as the source defines them
  (including the undocumented `EDUCATION` 0/5/6) rather than silently remapped.
- **Say:** one contract in three places is why the demo's rejected upload and the prediction form
  reject the same things for the same reason.

### Slide 5 — EDA: four findings that changed the modelling

- **On screen:** (a) the 77.88% majority class — a constant answer already scores 77.88%;
  (b) mean age 35.42 vs 35.73 years — almost no univariate signal, so no demographic story;
  (c) median credit limit 150,000 NTD (no default) vs 90,000 NTD (default), with heavy overlap;
  (d) default rate by `PAY_0` rises from 12.81% at code 0 to 69.14% at code 2 and 75.78% at
  code 3 — the strongest single relationship in the data; (e) the six balance columns are
  near-duplicates: `BILL_AMT1`–`BILL_AMT2` r = 0.9515.
- **Say:** (a) is why accuracy is not our criterion, (d) is why the tree is mostly learning one
  variable — said out loud on slide 11 — and (e) is why a linear model's coefficients cannot be
  read as independent effects.

### Slide 6 — Methodology: split, candidates, selection rule

- **On screen:** stratified 80/20 split, `random_state=42`: **24,000** training rows
  (18,691 / 5,309) and **6,000** held-out rows (4,673 / 1,327). Three candidates: logistic
  regression, decision tree, random forest. Selection by **mean 5-fold CV F1 on the training rows
  only**; ties within 0.005 broken by CV recall then CV precision; the held-out rows take no part
  in the choice. Cross-validated result: F1 **0.4643 ± 0.0138** (tree), **0.4191** (forest),
  **0.3647** (logistic); ROC-AUC 0.7555 / 0.7765 / 0.7261.
- **Say:** the rule is written before the results are seen, and the held-out set is scored once.

### Slide 7 — Why not accuracy: the held-out comparison and the errors it costs

- **On screen:** held-out comparison, threshold 0.50:

  | Model | Accuracy | Precision | Recall | F1 | ROC-AUC |
  |---|---:|---:|---:|---:|---:|
  | Decision tree (deployed) | 0.8172 | 0.6611 | 0.3557 | 0.4625 | 0.7423 |
  | Random forest | 0.8122 | 0.6773 | 0.2879 | 0.4040 | 0.7665 |
  | Logistic regression | 0.8077 | 0.6868 | 0.2396 | 0.3553 | 0.7076 |
  | Constant "no default" baseline | 0.7788 | 0.0000 | 0.0000 | 0.0000 | 0.5000 |

  Under it, the same three candidates as confusion matrices over the 6,000 held-out rows —
  decision tree TN **4,431**, FP **242**, FN **855**, TP **472**; random forest 4,491 / 182 /
  945 / 382; logistic regression 4,528 / 145 / 1,009 / 318.
- **Say:** the deployed tree is **+0.0383** accuracy (0.817167 − 0.778833) over a model that
  answers "no default" to everything and finds nothing; the random forest has the best ROC-AUC
  (0.7665) but a worse F1 (0.4040 against 0.4625), and we report that disagreement rather than
  hiding it. The errors are the rest of the story: it catches 472 of the 1,327 accounts that
  actually defaulted and misses 855 (64.4%), and those 855 false negatives are the number that
  matters operationally — this system is a screening aid, and a "no default" score is not a
  promise of payment.

### Slide 8 — Architecture: one container, one contract, no host ports

- **On screen:** Streamlit app → verified joblib pipeline (artifact SHA-256
  `48ce02563b2aad9fbf9397603c642b0319be617c57fde8e1fd26ec08d518ad7b`, 8,187 bytes) → SQLite
  (users, sessions, audit, predictions, dataset versions, rejections) → Cloudflare tunnel →
  `https://www.aihubcampus.online`. No published host port: the compose service is
  `expose: 2026` on an internal network and the ingress targets `http://web:2026`. Read-only
  root filesystem, all capabilities dropped, one writable volume.
- **Say:** the model is loaded from a file whose hash is checked at startup; if the hash does not
  match the manifest, the app refuses to predict instead of guessing.

### Slide 9 — Admin module: what an administrator can and cannot do

- **On screen:** create accounts, change role, reset a password, deactivate (deactivation keeps
  the audit trail); dataset manager stages a validated upload with an aggregate preview and
  activates a version explicitly; a rejected upload is recorded with a stable error code. Every
  action is audited. No password hash is ever rendered.
- **Say:** an upload never retrains and never replaces the live model — that is a deliberate
  boundary, and the demo shows it.

### Slide 10 — User prediction demo: one account, scored end to end

- **On screen:** the user's own sidebar — Home, Predict default risk, My prediction history, and
  nothing else — then the form: all **23** contract features in the four documented groups,
  *1 · Credit profile* (5: `LIMIT_BAL`, `SEX`, `EDUCATION`, `MARRIAGE`, `AGE`), *2 · Repayment
  history* (6: `PAY_0`, `PAY_2`–`PAY_6`), *3 · Billing amounts* (6: `BILL_AMT1`–`BILL_AMT6`),
  *4 · Previous paid amounts* (6: `PAY_AMT1`–`PAY_AMT6`). One button loads the synthetic
  demonstrator row, one button scores it. The result panel shows estimated probability
  **71.95%**, band **High**, the advice line, decision threshold **0.50**, model version
  `aihubcampus-default-risk-1+48ce02563b2a` and the recorded time. The same form submitted with
  `LIMIT_BAL` left empty is refused before the model is called — feature `LIMIT_BAL` has no
  value — so nothing is scored and nothing is recorded. My prediction history then lists only
  this account's own rows.
- **Say:** this is the whole journey an ordinary user gets: type an account, get a probability
  and a band with the threshold and model version printed next to it, see the invalid input
  refused rather than guessed at, and see the run in your own history — and nobody else's.

### Slide 11 — Ethics, fairness and limitations

- **On screen:** uncalibrated probabilities (no calibration test has been run); `SEX`, `EDUCATION`
  and `MARRIAGE` are in the feature set as the source provides them, and fairness is **not
  established**; `PAY_0` carries 68.01% of the tree's importance and `PAY_2` 13.77%, so the model
  mostly formalises a rule a reviewer already applies; 2005 Taiwanese data, so no claim about any other population;
  no real customer data may be entered.
- **Say:** these are the four sentences we would want an examiner to hold us to.

### Slide 12 — Conclusion and what we would do next

- **On screen:** a live system that scores an account end to end, an evaluation that can be
  re-run from the committed artefacts, and a written record of what it cannot do. Next:
  calibration on a held-out set, a cost-sensitive threshold instead of 0.5, and a fairness audit
  before any use beyond coursework.
- **Say:** the deliverable is the evidence trail as much as the app.

## 15.3 The live demo — twelve steps, exact values, expected results

Target: `https://www.aihubcampus.online`. Two accounts are needed: an administrator and the demo
user. **The demo-day administrator credential belongs to the operator**; the rehearsal used a
synthetic administrator created for the run and deactivated afterwards, because this sprint must
not rewrite the operator's credential. Confirm the administrator password before the session
starts, and keep it off the slide.

| # | Action | Exact input | Expected on screen | Planned | Rehearsed |
|---|---|---|---|---:|---:|
| 1 | Open the URL | `https://www.aihubcampus.online` | Streamlit shell, then the sign-in form (first paint 3.6 s in the recorded run) | 10 s | 5.5 s |
| 2 | Administrator signs in | the operator's admin username and password | sidebar shows **six** sections: Home, Predict default risk, My prediction history, User management, Dataset manager, Model evaluation | 20 s | 3.9 s |
| 3 | User management | none — read the page | the account list includes `ds_hafyz` and `demo_user`; the controls for create / role / temporary password / deactivate are present; **no password hash anywhere on the page** | 20 s | 2.8 s |
| 4 | Dataset validation, refusal | upload a 25-column CSV with `PAY_AMT6` removed | red: *missing required column(s): PAY_AMT6; the file must contain all 25 documented columns*; a rejection id and the code `missing_column`; the caption *nothing was cleaned, coerced or partially loaded* | 40 s | 26.5 s (both uploads) |
| 5 | Dataset validation, acceptance | upload the same rows with all 25 columns | green: *Staged as dataset version #N. It is validated and quarantined …; it is **not** active and the deployed model has not changed.* | 30 s | (in the 26.5 s above) |
| 6 | Administrator signs out | Sign out | the sign-in form returns | 10 s | 4.9 s |
| 7 | User signs in | `demo_user` and its password | sidebar shows **three** sections only — Home, Predict default risk, My prediction history | 15 s | 2.8 s |
| 8 | Load the demonstrator | press **Load synthetic demonstrator example** | the 23 inputs fill with the values in §15.3.1 | 15 s | 10.0 s |
| 9 | Score it | press **Predict default risk** | **71.95%** estimated probability of default, band **High**, advice *Offer supportive contact and discuss potential payment arrangements.*, threshold **0.50**, model version `aihubcampus-default-risk-1+48ce02563b2a` | 15 s | (in the 10.0 s above) |
| 10 | Refuse an invalid request | **Clear result**, empty the *Credit limit* field, press **Predict default risk** | red: *feature 'LIMIT_BAL' has no value*, then *The request was rejected before the model was called: nothing was scored and nothing was recorded.* My prediction history stays at the same row count | 30 s | 19.7 s |
| 11 | Model evaluation (administrator) | sign in as the administrator, open **Model evaluation** | six sections; the Limitations panel states accuracy **0.817167**, recall **0.356**, *missed 855*, the 1,327 actual defaults and the constant-answer **77.88%**; eleven figures and the comparison grids paint | 30 s | 12.9 s |
| 12 | Sign out | Sign out | the sign-in form returns | 5 s | 3.8 s |

Two things about this table are worth knowing before the session.

- **The first paint is the slow part.** A cold Streamlit session behind the Cloudflare edge
  measured **32.4 s** on an earlier attempt (§15.4); in the recorded run the first paint was
  **3.6 s** and step 1 took **5.5 s** (table row 1). Open the URL *before* you start talking
  about the deck, or accept a pause.
- **The same request twice is not logged twice.** If the demonstrator row has already been scored
  by that account in the same session, the result panel says so and does not write a second row.
  That is a feature; if you want a fresh write, change one field (for example `AGE` to 35).

### 15.3.1 The 23 demonstrator values

The page's own button loads exactly these; the rehearsal read all 23 back off the rendered widgets,
not out of session state.

| Field | Value | Field | Value |
|---|---:|---|---:|
| `LIMIT_BAL` | 120000 | `BILL_AMT1` | 35000 |
| `SEX` | 2 — female | `BILL_AMT2` | 33500 |
| `EDUCATION` | 2 — university | `BILL_AMT3` | 30000 |
| `MARRIAGE` | 2 — single | `BILL_AMT4` | 28000 |
| `AGE` | 34 | `BILL_AMT5` | 26500 |
| `PAY_0` | 2 — two months of delay | `BILL_AMT6` | 25000 |
| `PAY_2` | 2 — two months of delay | `PAY_AMT1` | 2000 |
| `PAY_3` | 0 — revolving credit | `PAY_AMT2` | 2500 |
| `PAY_4` | 0 — revolving credit | `PAY_AMT3` | 3000 |
| `PAY_5` | -1 — paid in full | `PAY_AMT4` | 3000 |
| `PAY_6` | -1 — paid in full | `PAY_AMT5` | 3500 |
| | | `PAY_AMT6` | 4000 |

## 15.4 The rehearsal: what actually happened

`evidence/s15/demo_rehearsal.txt` is the transcript of the recorded run; the driver is
`evidence/s15/run_demo_rehearsal.sh` and the browser journeys are
`evidence/s15/ui_demo_rehearsal.js`. The run drove the public hostname with a real Chromium —
nothing in it talks to the container directly — and wrote one screenshot per step
(`s15_01_signin.png` … `s15_09_model_evaluation.png`).

- **Result of the recorded run:** 33 checks, 0 failed, `verdict: PASS`, 96.7 s of measured
  on-screen time, at `HEAD` `3860aef` on branch `s15/presentation-demo-qa` with the S15 files in
  the working tree (the transcript records that `HEAD` itself, so a later commit is a later run).
- **Flakiness, recorded rather than smoothed:** earlier attempts failed and their failures are
  why the driver now waits for the widget instead of the page text. One attempt hit a **32.4 s**
  first paint and then no sign-in input within 30 s; one attempt died on
  `net::ERR_NETWORK_CHANGED` before the first paint; two attempts pressed *Validate and stage*
  before the 27 KB upload had crossed the tunnel and were answered *Choose a CSV file first* — a
  correct answer to a premature click. The driver retries each of those once; the final run
  needed none of the retries.
- **What the rehearsal could not read:** the comparison table, the confusion matrices and the
  per-upload fact table are `st.dataframe` grids, so their cell values are painted, not text in
  the page. The transcript therefore asserts the prose the page writes from the same metrics (the
  Limitations panel) and that the grids paint, and `check_script_numbers.py` checks the figures in
  this document against `models/metrics.json` directly.
- **What the rehearsal changed in the app:** nothing. It wrote one prediction row for `demo_user`,
  one rejected upload and one staged dataset version in the live database, and left the deployed
  model, the active dataset and the operator's credential untouched.

## 15.5 Q&A bank

Eight topics, each with the answer that is correct for *this* system. Where the honest answer is
"we did not do that", it says so.

**1. "Your accuracy is 81.72% — isn't that barely better than guessing?"**
Correct, and it is the question the project is built to answer honestly. The majority class is
77.88%, so a constant "no default" answer already scores 77.88% and catches nothing. The deployed
tree is +0.0383 accuracy over that, and the numbers that carry the work are F1 **0.4625**,
recall **0.3557** and precision **0.6611** at threshold 0.50: it finds 472 of the 1,327 accounts
that defaulted, and of the 714 it flags, 242 (33.9%) would not have defaulted. We report
accuracy, precision, recall, F1 and ROC-AUC together, and the selection rule used CV F1, not
accuracy.

**2. "Is the model overfitted?"**
The evidence says not materially: mean 5-fold CV F1 on the training rows is **0.4643 ± 0.0138**
and the held-out F1 is **0.4625** — a gap of 0.0018, well inside one fold's standard deviation.
A single decision tree can overfit; what protects the reported numbers is that the shipped
pipeline fixes `max_depth=5`, `random_state=42` — a shallow, constrained tree, not an unpruned one
— and that the held-out 6,000 rows were scored once, after selection.

**3. "Did you leak the target or the test set?"**
The target column `default.payment.next.month` and `ID` are dropped before fitting, and the split
is made before any preprocessing is fitted — the pipeline carries the transform, so it is fitted
on training rows only. Cross-validation runs on the 24,000 training rows; the held-out 6,000 take
no part in selection (`test_rows_used_for_selection: 0`). The one leakage-adjacent thing we do
disclose: `PAY_0`…`PAY_6` are historical repayment statuses, which is legitimate as a predictor of
next month's default but does mean the model is largely reading recent behaviour.

**4. "Class imbalance — what did you do about it?"**
Nothing to the data: no resampling, no synthetic rows, no class weights. We changed the
*criterion* instead — selection by CV F1 on the default class, ties broken by recall — and we
report the confusion matrix rather than a single score. The consequence is visible and stated:
precision is 0.6611, so about a third of the accounts flagged at this threshold would not have
defaulted. A cost-sensitive threshold is listed as future work, not claimed as done.

**5. "Is the probability calibrated? Can we read 71.95% as a 72% chance?"**
No. The number is the model's own score at threshold 0.50 and **no calibration test has been
run**; the page says "estimated, uncalibrated" next to it. Reading it as a probability of default
would be wrong. Calibration on a held-out set is the first item in the "what next" list.

**6. "How do you know the person seeing a prediction is allowed to see it?"**
Every page re-checks the session server-side — the sidebar is a convenience, not the control. A
user's history query is scoped to their own account id, so a hand-made request cannot read another
account's rows. Roles are checked per page: the user navigation offers three sections and the
administrator six, and the rehearsal asserted both. Passwords are stored as Argon2id hashes and no
hash is rendered anywhere; sessions are server-side rows with expiry.

**7. "Ethics: you use sex, education and marital status. Isn't that discriminatory?"**
It is a real risk and we do not claim otherwise. The features are in the source and in the model;
fairness is **not established** — no group-wise error analysis has been run, and the page and the
report say so. The model makes no decision: it shows a score and a suggested next step to a human,
on 2005 Taiwanese data, and the system refuses to be described as a credit decision. A fairness
audit before any use beyond coursework is the honest position, and it is written into the
limitations rather than left implicit.

**8. "Deployment: what happens if the model file is corrupted or swapped?"**
At startup the app hashes the artifact and compares it with the manifest (SHA-256
`48ce02563b2aad9fbf9397603c642b0319be617c57fde8e1fd26ec08d518ad7b`). On a mismatch it refuses to
predict and records the failure in the build information instead of serving a different model. The
container runs read-only with all capabilities dropped and no host ports; the only public path is
the Cloudflare tunnel, and no host port is published. An uploaded dataset never becomes training
data inside the app — staging and activation are metadata moves, and retraining is an operator
action outside the page.

**Spare answers, if the examiner pushes further**

- *Why a decision tree and not the random forest?* CV F1 0.4643 vs 0.4191 — the tree wins on the
  criterion chosen before the results were seen. The forest has the better ROC-AUC (0.7765 vs
  0.7555 cross-validated; 0.7665 vs 0.7423 held out) and a worse F1, and we report that
  disagreement instead of hiding it.
- *Why threshold 0.50?* Because it is the evaluated threshold and changing it without re-evaluating
  would invalidate the reported confusion matrix. The threshold is displayed on every result.
- *Why SQLite?* Single-container coursework deployment with no concurrent-writer requirement;
  PostgreSQL was explicitly out of scope.
- *What is the biggest weakness?* `PAY_0` carries 68.01% of the tree's importance: the model
  mostly formalises "an account two months late is likely to default again", which a reviewer
  already knows.

## 15.6 Who presents what — unconfirmed

The blueprint's acceptance criterion is *actual team assignments confirmed rather than invented*,
and this repository does not contain the group's membership or the division agreed between them.
The table below is therefore a **proposal with blanks**, not a record. Fill it in from the group's
own agreement and delete this paragraph; no agent should invent names or roles here.

| Block | Slides / steps | Presenter | Confirmed? |
|---|---|---|---|
| Problem, objectives, scope | 1–2 | | no |
| Dataset, preprocessing, EDA | 3–5 | | no |
| Methodology and results | 6–7 | | no |
| Architecture and admin demo | 8–9, steps 2–6 | | no |
| User prediction demo | 10, steps 7–10 | | no |
| Model evaluation and sign-out | steps 11–12 | | no |
| Ethics, limitations, conclusion | 11–12 | | no |
| Q&A lead per topic (§15.5) | 1–8 | | no |

## 15.7 What this document does not claim

- **It does not claim a rehearsed presentation.** The demo was rehearsed against the live site;
  the speaking was not. Timing is a planning assumption (§15.1).
- **It does not claim the deck exists as slides.** This is the outline and the speaker notes; no
  `.pptx` was produced, because the deck's visual design is a group decision.
- **It does not claim team roles.** §15.6 is unconfirmed by construction.
- **It does not claim a screencast.** Nine screenshots of the live site exist under `evidence/s15/`;
  whether recording is permitted is the lecturer's call.
- **It does not claim the demo cannot drift.** It can — the deployed model or the demo account can
  change between now and the session. The rehearsal record states the commit it ran at, so drift is
  detectable rather than invisible.
