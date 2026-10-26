# AI Hub Campus — Credit Card Default Risk Prediction System
## MASTER BLUEPRINT: Sprint 0 → Production-Level Academic Demonstration

**Version:** 1.0 | **Date:** 2026-10-26 | **Status:** IMPLEMENTATION SPECIFICATION (not a claim of completed work)

> **Instructions to Hermes (orchestrator) and Multica (builder):** Implement this specification in ordered, verifiable sprints. Deliver a simple, functional, maintainable academic web application—not an enterprise banking system. Never declare a sprint complete until its acceptance criteria and evidence exist. Do not invent experimental metrics, test passes, screenshots, deployment outcomes, dates or group contributions. Do not touch unrelated projects, containers, data, networks, tunnels or DNS records. Seek user authorization before affecting a live host/domain, changing DNS, or deploying to a shared server. Never commit any secret or raw credential.

---

## 0. Primary mandate and source of truth

### Project and purpose
- Name: **AI Hub Campus — Credit Card Default Risk Prediction**.
- Academic topic: **Development of a Credit Card Default Risk Prediction System Using Machine Learning Classification Algorithms**.
- Sector: Finance. Problem: support earlier identification of credit card customers who may default on their next payment; output decision-support recommendations, **not automatic adverse financial decisions**.
- Prediction: **binary**; target `default.payment.next.month`: `0` = no default next month, `1` = default next month.
- Public hostname: **https://www.aihubcampus.online**.
- Deployment: **Docker Compose**, privately networked **Cloudflare remotely-managed Tunnel**; operator inserts token in `.env`.
- Initial username: `web`; initial password: **provided by operator securely** (never embedded in image, tracked file or logs). Login credentials supplied verbally are not permission to hardcode them.
- Mandatory functional split: **Admin and User** roles; a real sign-in and backend authorization mechanism, not merely UI role selectors.
- Intended scope: **simple web app**, thorough ML evidence and testing, reproducible production-like deployment.

### Sources and priority
1. `Group Project 40%.md` is the assessment authority (report 20%, presentation/system demo 20%).
2. `Credit_Card_Default_Prediction_Project-v3.docx` is the detailed project draft and starting design, not automatically verified evidence.
3. `Credit_Card_Default_Prediction_Project.docx` is earlier draft for context; resolve conflicts in favor of assessment and verified executions.
4. `UCI_Credit_Card.csv` is the actual uploaded dataset and must be inspected by code rather than guessed.
5. Current reproducible run output takes precedence over any draft's historical numerical claims.

**Verified uploaded CSV facts (direct read):** 30,000 rows, 25 columns, 0 missing cells, 0 duplicated full rows; class 0 = 23,364 (77.88%), class 1 = 6,636 (22.12%). Schema is recorded in §4. Dataset source attributed to UCI ML Repository, *Default of Credit Card Clients*, Yeh & Lien (2009); describe the historical Taiwanese credit context and monetary amounts in **New Taiwan Dollars (NTD)**, not MYR/USD. No individual identity or banking account information should be collected.

**Draft v3's reported model results (REFERENCE ONLY—MUST REPRODUCE):**

| Model | Accuracy | Precision (default=1) | Recall (default=1) | F1 (default=1) |
|---|---:|---:|---:|---:|
| Logistic Regression | 0.8077 | 0.6868 | 0.2396 | 0.3553 |
| Decision Tree | 0.8172 | 0.6615 | 0.3549 | 0.4620 |
| Random Forest | 0.8122 | 0.6773 | 0.2879 | 0.4040 |

v3 selects a Decision Tree (max_depth=5) and quotes 81.72% accuracy / 35.49% recall. **Do not claim reproduced until an exact training environment, split seed, code and test confusion matrices verify it.** Even if metrics vary, publish the observed metrics and a documented selection rationale; retain Decision Tree if acceptable with clear reason, otherwise document and justify revised selection. **Do not tune on held-out test set.** Its 35.49% recall means substantial missed defaults, an important limitation. A 77.88%-accuracy majority-class baseline is mandatory for comparison.

### No-go decisions
- No Next.js, React SPA, separate FastAPI backend, PostgreSQL, Redis, Kubernetes, Celery, paid ML APIs, LLM, automated bank/customer actions, registration or email system.
- No training the model at every page refresh/request.
- No unreviewed `joblib`/pickle uploads or execution of uploaded code.
- No direct public host port; access through Cloudflare Tunnel only. Optional local `127.0.0.1:8501` bind for troubleshooting must be explicitly enabled, otherwise no `ports` section.
- Do not present scores as calibrated statistical guarantees, a credit score or ground-truth outcome.
- No demo/test account with permanent publicly documented password. No user-provided tunnel token in this file.

---

## 1. Definition of done / user journey

A reviewer navigates to `https://www.aihubcampus.online`, signs in to a genuine session, and is served an appropriate dashboard:

**User journey**
1. Login with user account; unauthenticated pages are blocked.
2. Open **Predict Default Risk**; view a clean 23-feature form organized into Credit Profile, Demographics, Repayment Status, Monthly Bills, Monthly Payments.
3. Optionally load a **synthetic demonstrator example** (not a real person's row, and clearly labeled); can edit every field.
4. Enter/validate 23 fields, submit to real saved ML pipeline.
5. See predicted next-month default class (0/1), model-derived `predict_proba` value, plain-language risk explanation, 1–2 supportive recommendations, disclaimer and model version.
6. Open **My Prediction History** for own submissions; sign out. Historical predictions do not assert that real defaults occurred.

**Admin journey**
1. Login with admin credentials; all user features also available.
2. **Manage Users**: list, create, edit display name/role/active status, reset password, deactivate; never expose password hashes or allow deleting last enabled admin. Soft deactivation preferred.
3. **Dataset Manager**: view active training dataset metadata, class balance and schema; upload a CSV to temporary quarantine, validate 25 required columns/types/ranges/target/class counts, preview an anonymized aggregate and choose **Activate Dataset** explicitly. Never auto-run retraining upon mere upload; dataset versioning/checksum and audit trail.
4. **Model Performance**: view actual Logistic Regression / Decision Tree / Random Forest metrics, confusion matrices, selected deployed model, training timestamp/hash and methods. Show 6 EDA plots with interpretations.
5. **System Overview**: datasets/models/users/predictions counts, health, recent auditable admin actions, model artifact version.
6. Optional manual **Retrain** only after separately reviewed data activation; must preserve rollback and never replace active artifact on failure. This is a stretch objective; a reproducible CLI retraining command is sufficient for the assignment if admin dataset management functions work.

**Review demonstration requirements:** both Admin and User operate end-to-end; actual ML output matches direct pipeline inference; valid CSV accepted and invalid CSV rejected; role bypass fails; restart preserves SQLite and active model.

---

## 2. Minimal technology architecture

| Layer | Technology | Justification |
|---|---|---|
| Web/UI | Python 3.12 + pinned Streamlit release | Quick responsive academic interface, Python-native ML integration |
| Data and EDA | pandas, NumPy, matplotlib | Clean, reproducible exploration |
| Machine learning | scikit-learn, joblib | 3 classification pipelines; trained artifact load |
| Storage | SQLite (persistent Docker named/bind volume) | Low overhead, adequate single-instance school demo |
| Authentication | Python `argon2-cffi` or `bcrypt` password hashing, signed/session-check safeguards | Do NOT use unsalted bare SHA-256 hashes from older draft |
| Testing | pytest + Streamlit AppTest where practical; Playwright optional for browser | Observable objective gates |
| Deployment | Dockerfile + Compose + `cloudflare/cloudflared` | Reproducible, no publicly opened ingress port |
| Reverse proxy | Cloudflare Tunnel, remotely managed | External HTTPS on requested domain |

Architectural path:

```text
Browser (HTTPS)
  -> Cloudflare edge / public hostname www.aihubcampus.online
  -> remotely-managed Cloudflare Tunnel (outbound only)
  -> cloudflared container -- Docker internal network --> Streamlit :8501
  -> session/auth/role guard + input validation
  -> pinned joblib Pipeline (same training feature ordering)
  -> classification + predict_proba + safe recommendation mapping
  -> SQLite users / dataset versions / prediction log / audit

Offline/reproducible build path:
Uploaded UCI_Credit_Card.csv -> validation -> EDA -> stratified train/test
 -> 3 model pipelines -> independent evaluation -> selected artifact + metadata
 -> app loads verified artifact read-only; no runtime training on predictions
```

**Network rule:** `cloudflared` must access `http://web:8501` inside the same Compose network. The literal `web` used as application hostname corresponds to the Docker Compose service name **web**, not the admin username. Use a single instance of the Streamlit app and SQLite to avoid concurrent-session ambiguity. Set Cloudflare published application hostname `www.aihubcampus.online` → `http://web:8501` in the Tunnel dashboard; this Cloudflare-side configuration is necessary in addition to starting the container. Configure DNS for that hostname through the Tunnel wizard and ensure no conflicting existing record. Decide whether apex `aihubcampus.online` redirects to `www`, if DNS is under operator control.

### Security / operational defaults
- Streamlit `server.address=0.0.0.0`, port `8501`, `headless=true`, `enableCORS=true`, `enableXsrfProtection=true`. Configure `browser.serverAddress=www.aihubcampus.online` and `browser.serverPort=443` if required for proxy support. Verify websocket sessions, login and file uploads through Cloudflare in browser; do not indiscriminately disable XSRF/CORS to 'fix' connectivity.
- Session identity stored server-side or in hardened signed tokens with expiry; ensure Streamlit session state alone is not treated as unconditional authorization. Validate role in every privileged function; enforce session expiry, logout and user deactivation. Block unauthorized data fetches and duplicate submissions.
- Passwords hashed with Argon2id/bcrypt using vetted libraries and constant-time verification; rate-limit bad logins (simple SQLite-backed attempt counters with expiry or suitable lightweight mechanism). 8–12+ characters minimum for new passwords; initial operator-specified password must be rotated if weak.
- SQLite file directory writable only by application account; DB and model not exposed as static files. Use parameterized SQL. Restrict uploaded CSV size (e.g. 10 MB) and MIME/extension **plus parse/schema validation**, and ensure no CSV formula content is later opened as an unsafe spreadsheet export.
- Never log raw 23-feature submissions, credentials, password hashes, token or sensitive cookie values. History is pseudonymous by internal user ID with restricted access; allow admin retention cleanup; set retention to 30 days for demo logs by default.
- Disclaimer: historical Taiwanese 2005 dataset, observational statistical model, not financial advice or automatic credit decision. Treat demographic features as fairness risks; in report discuss their usage and a possible exclusion/ablation study. Do not claim model is fair without evaluation.

---

## 3. File layout / responsibilities

```text
aihubcampus/
├── README.md
├── blueprint.md
├── .gitignore
├── .dockerignore
├── .env.example                 # placeholder only; NEVER real token/password
├── compose.yaml
├── Dockerfile
├── requirements.in              # human-edited direct dependencies
├── requirements.txt             # pinned/locked dependencies
├── .streamlit/config.toml
├── app.py                       # navigation, authenticated page dispatch
├── src/
│   ├── config.py                 # typed environment settings
│   ├── db.py                     # SQLite connection + migrations
│   ├── security.py               # hashing, session, RBAC, login throttling
│   ├── validation.py             # dataset and 23-feature schema
│   ├── inference.py              # cached verified pipeline and prediction
│   ├── recommendations.py        # consistent rule-based support advice
│   ├── data_manager.py           # dataset versioning and checksums
│   ├── charts.py                 # render saved EDA/performance evidence
│   ├── pages_login.py
│   ├── pages_prediction.py
│   ├── pages_history.py
│   ├── pages_admin.py
│   ├── pages_evaluation.py
│   └── audit.py
├── ml/
│   ├── inspect_dataset.py
│   ├── generate_eda.py
│   ├── train.py
│   ├── evaluate.py
│   ├── schema.py
│   └── verify_artifact.py
├── data/
│   └── UCI_Credit_Card.csv      # supplied dataset; provenance in README
├── models/
│   ├── best_pipeline.joblib     # generated from controlled trusted code
│   ├── metrics.json
│   ├── model_manifest.json
│   └── eda/                      # generated 6 plots
├── tests/
│   ├── test_schema.py
│   ├── test_preprocessing.py
│   ├── test_model.py
│   ├── test_security.py
│   ├── test_admin.py
│   ├── test_prediction.py
│   └── test_integration.py
├── scripts/
│   ├── init_admin.py
│   ├── smoke_test.sh
│   ├── backup.sh
│   ├── restore.sh
│   └── verify_release.sh
├── docs/
│   ├── architecture.md
│   ├── data_dictionary.md
│   ├── model_card.md
│   ├── test_matrix.md
│   ├── runbook.md
│   ├── deployment.md
│   ├── rubric_matrix.md
│   ├── report_evidence.md
│   ├── presentation_script.md
│   └── RELEASE_NOTES.md
└── evidence/
    ├── screenshots/             # capture actual running system only
    ├── test-results/
    └── reports/                  # generated outputs, no fabricated scores
```

Do not create massive scaffolding with dead files; combine modules only when it improves simplicity, while preserving testability and expected deliverables. All actual implementation details and deviations must be recorded in `docs/architecture.md`.

---

## 4. Dataset schema, preprocessing and input contract

Uploaded source has exactly:

```text
ID, LIMIT_BAL, SEX, EDUCATION, MARRIAGE, AGE,
PAY_0, PAY_2, PAY_3, PAY_4, PAY_5, PAY_6,
BILL_AMT1, BILL_AMT2, BILL_AMT3, BILL_AMT4, BILL_AMT5, BILL_AMT6,
PAY_AMT1, PAY_AMT2, PAY_AMT3, PAY_AMT4, PAY_AMT5, PAY_AMT6,
default.payment.next.month
```

- `ID`: technical dataset identifier; exclude from training and user form.
- `default.payment.next.month`: target; exclude from inference form and model features.
- Remaining **23 attributes**, in listed exact order, are the feature contract. Save in manifest and validate request against it.
- `LIMIT_BAL`: nonnegative/positive realistic NTD credit limit; demo accepted band should encompass observed dataset range (10,000–1,000,000 NTD). Avoid rejecting known valid dataset values; document form constraints.
- `SEX`: dataset code 1/2; UI can label original codes without inferring gender identity beyond dataset coding; never use to drive discriminatory recommendations.
- `EDUCATION`: original codes can include 0/5/6; do not silently replace or reject legitimate dataset codes. If grouping categories, document and apply identical transform at training and inference.
- `MARRIAGE`: source codes can include 0; handle it explicitly as unknown/other per documented normalization.
- `AGE`: dataset observed 21–79; UI validation must not accept impossible/non-numeric entries. Avoid over-restricting to observed min/max for future inputs without documenting choice.
- `PAY_0`, `PAY_2`…`PAY_6`: **six** status columns; do NOT invent `PAY_1`. Preserve negative repayment status codes; validate against actual observed data and accepted source semantics.
- `BILL_AMT1..6`: signed NTD amounts; **negative bills may be valid**, do not unconditionally reject.
- `PAY_AMT1..6`: nonnegative payments (unless verified otherwise).
- Each numerical field uses defined unit/description and month (PAY_0 most recent September, PAY_2 August, … PAY_6 April in the source dataset).
- CSV validator: reject missing/extra required columns according to policy, duplicate column headers, wrong target values, non-finite values, unsupported codes, overlarge files and empty data; report actionable errors without leaking data. Do not apply destructive cleaning silently. On admin upload, do not trust uploaded filename for storage paths; generate controlled name and checksum.
- Data leakage prevention: remove ID/target; stratified 80/20 split (`random_state=42` chosen for reproducibility, not assumed to match v3); **fit preprocessing only on training folds** via scikit-learn `Pipeline`/`ColumnTransformer`, then transform test set. Compare fair equivalent splits and feature ordering. If categorical encoding is used, train & serve same transformer. Scale numeric values for Logistic Regression where useful; tree models do not require scaling, although using a consistently documented scaler is allowed for reproducing draft.
- Preserve original dataset untouched as immutable seed for reproducing benchmark. Newly activated admin datasets are separate versions and cannot silently replace the benchmark report evidence.

### UI form grouping (23 inputs)
1. **Customer profile (5):** LIMIT_BAL, SEX, EDUCATION, MARRIAGE, AGE.
2. **Repayment history (6):** PAY_0, PAY_2, PAY_3, PAY_4, PAY_5, PAY_6.
3. **Billing amounts (6):** BILL_AMT1 through BILL_AMT6.
4. **Previous paid amounts (6):** PAY_AMT1 through PAY_AMT6.

Use accordions/tabs and inline explanatory text so this large form remains manageable on phones. Never reduce 23 input features to a handful unless a separately trained reduced-feature model is correctly documented and evaluated.

---

## 5. Machine-learning experimental protocol

### Mandatory training program
1. Verify dataset integrity, size, target labels, class distribution, nulls, duplicate rows, dtypes, outliers and source provenance.
2. Create descriptive statistics and six EDA visualizations with **interpretive captions**: (a) target class distribution, (b) age by class boxplot, (c) limit balance by class, (d) PAY_0 by default rate, (e) education by default rate, (f) financial feature correlation heatmap. Note any small-category instability and that correlations do not establish causality.
3. Use a deterministic **stratified 80/20 split**, keep test data held out (24k/6k for baseline). Store random state and package versions. Optional cross-validation on train set for hyperparameter selection without accessing test.
4. Fit three classifiers: **LogisticRegression** (appropriate `max_iter`, scaling pipeline), **DecisionTreeClassifier(max_depth=5)** and **RandomForestClassifier(n_estimators=100, max_depth=5)** as baseline settings from v3; use fixed random state where applicable.
5. Calculate on same untouched held-out test: accuracy, precision (positive label 1), recall (positive label 1), F1, confusion matrix TN/FP/FN/TP, ROC-AUC where probabilities exist; compare to always-class-0 baseline.
6. Model selection prioritizes **F1 and default-class recall** balanced against precision and false positives; document tradeoffs. No selecting only on accuracy with class imbalance. For strict unbiased evaluation, use train-only cross-validation to select model, then one final held-out test assessment.
7. Save selected complete fitted pipeline to `models/best_pipeline.joblib`; save `metrics.json` with dataset SHA256, train/test seeds/counts, hyperparameters, evaluation outputs and timestamps, package versions; save `model_manifest.json` with expected ordered features, class semantics and threshold (default 0.5). Verify artifact checksum and trusted creation path.
8. Verify loaded pipeline reproduces fresh inference result before wiring UI. Model requires no training during request handling.
9. Show class 0 as '**Predicted non-default next month**', NOT guaranteed payment; class 1 '**Predicted default next month**', NOT confirmed delinquency. Label probability `Estimated model probability of next-month default`; confidence/probability is uncalibrated unless tested for calibration.
10. Make model's false-negative risk explicit; ideally display a note: benchmark recall ~35% **only if reproduced**. Keep prediction threshold fixed at evaluated value. Alternative thresholds require train/validation-only selection and new evaluation evidence.

### Recommendation rules
Use separate, clearly described rule-based guidance **based on the model score**, not another hidden model. Proposed 4 display tiers (illustrative cutoffs, must document not validated banking thresholds):

| Estimated P(default) | Display tier | Supportive user-facing advice |
|---|---|---|
| 0.00–0.2499 | Low | Continue routine repayment reminders and periodic review. |
| 0.25–0.4999 | Watch | Review payment schedule and contact customer proactively with a neutral reminder. |
| 0.50–0.7499 | High | Offer supportive contact and discuss potential payment arrangements. |
| 0.75–1.00 | Critical | Recommend human risk/support specialist review before any action. |

Predicted class remains derived from the selected model's threshold. Tiers are **illustrative UI bands**, not regulatory credit classifications; avoid automated credit limit freeze or customer sanction. Ranges continuous, no gaps (especially 25%, 50%, 75%).

### Required ML artifacts
- `models/metrics.json` and readable model comparison table.
- Three genuine confusion matrices with labeled axes and numerical counts.
- At least six EDA plots with captions tied to actual data.
- Decision Tree feature importance chart **if tree selected**, or alternative explained for different chosen model.
- `docs/model_card.md`: data provenance, date/locale, intended users, limitations, chosen threshold, evaluation, biases, model/package version and reproducibility commands.
- `docs/report_evidence.md` separates verified observations and still-unverified claims in v3. Do not repeat v3's unsupported claim that age 'proves no significant effect' without significance testing; use 'similar distributions in this sample' unless tested.

---

## 6. Application design / routes

Streamlit multipage navigation may use page registration or internal dispatch, but **every page/function must check session and role server-side**. Suggested navigation:

| Section | User | Admin | Content |
|---|---|---|---|
| Login / Logout | yes | yes | user/password, error banner, session end |
| Home | yes | yes | friendly summary, role, model limitations |
| Predict | yes | yes | 23-field input, validation, ML output + advice |
| My History | yes | yes | user's prediction timestamp/results only |
| Admin Overview | no | yes | operational counts + recent audit events |
| User Management | no | yes | CRUD/deactivate, role controls, password reset |
| Dataset Manager | no | yes | source/version/preview/upload validation/activation |
| ML Evaluation & EDA | view-only optional | yes | 3-model comparison, figures, metrics, feature importance |
| Settings | no | yes | data retention/status, model metadata; no arbitrary code/settings |

### UI style
- Simple professional academic fintech aesthetic; navy/slate/teal neutral, consistent typography and clear white background. Responsive desktop + 375px mobile.
- Header: **AI Hub Campus**; subtitle: **Credit Card Default Risk Prediction**. Footer: **Academic decision-support demonstration · historical data · not a bank credit decision**.
- Home includes 3 concise explanation cards: data, ML comparison, prediction.
- Avoid giant hero/animation/complex marketing pages. Demo-focused navigation.
- Real chart captions show how they relate to risk rather than decorations.
- Clear labels show **NTD**, historical month mapping, code descriptions.
- No personal names/actual banking customers inserted in screenshots.

### Database design (SQLite)
- `users(id PK, username UNIQUE, display_name, password_hash, role CHECK(admin,user), is_active, created_at, updated_at, last_login_at)`.
- `prediction_logs(id PK, user_id FK, predicted_class, default_probability, risk_tier, model_version, created_at)`; optionally store feature snapshots **only if essential**, otherwise do not store raw details. Users may access only their own logs.
- `dataset_versions(id PK, original_filename_safe, sha256 UNIQUE, record_count, column_count, class_zero, class_one, validated_at, activated_at, is_active, uploaded_by FK, status)`; one active dataset enforced in transactions.
- `audit_events(id PK, actor_user_id FK, action, entity_type, entity_id, created_at, non_sensitive_details)`.
- `schema_migrations(version PK, applied_at)`; idempotent startup; DB placed at `/app/storage/aihubcampus.db` on volume.
- SQLITE WAL / busy timeout; transaction boundaries on create/update/activate, indexed user/time log listing.
- `init_admin.py`: create first admin **only when none exists**, reading `INITIAL_ADMIN_USERNAME` and **securely injected** `INITIAL_ADMIN_PASSWORD` from environment at setup time, then optionally remove from runtime config. Never overwrite an existing admin's password on restart. Use `web` as username; operator's password known, but write only to operator's `.env` locally, never into a committed file.

---

## 7. Docker and Cloudflare deployment contract

### `.env.example` (safe to commit)

```dotenv
APP_ENV=production
APP_DOMAIN=www.aihubcampus.online
INITIAL_ADMIN_USERNAME=web
INITIAL_ADMIN_PASSWORD=REPLACE_WITH_STRONG_OPERATOR_PASSWORD
TUNNEL_TOKEN=REPLACE_WITH_CLOUDFLARE_TUNNEL_TOKEN
APP_SESSION_SECRET=REPLACE_WITH_RANDOM_LONG_SECRET
DATA_RETENTION_DAYS=30
```

**Operator action:** copy `.env.example` to `.env`, supply their own actual password and Cloudflare token there; `chmod 600 .env`. `.gitignore` MUST include `.env`, `.env.*` excluding `.env.example`, Python caches, DB, logs, temp uploads and any operator backups. Do not echo token into CI output or `docker inspect` reporting. Environment secrets in Compose still appear in some host/container metadata: secure host access and restrict permissions. **The sample token supplied in chat is a secret even if called a test; rotate/revoke it before production because anyone possessing it can run the tunnel.** Do not print original token anywhere in files.

### `Dockerfile` implementation contract
- Pinned Python 3.12 slim or supported stable image, create non-root user; install pinned requirements with no unneeded build tool residue; copy only code, read-only model artifacts and config; writable volume for DB and temporary quarantine; use healthcheck on `http://localhost:8501/_stcore/health` using Python stdlib URL opener (no need curl).
- Launch app: `streamlit run app.py --server.address=0.0.0.0 --server.port=8501`.
- Never bake `.env`, dataset with user changes, credentials, SQLite or SSH keys into image.

### `compose.yaml` reference (agents must implement and validate)

```yaml
name: aihubcampus
services:
  web:
    build: .
    restart: unless-stopped
    env_file:
      - .env
    environment:
      APP_DB_PATH: /app/storage/aihubcampus.db
    volumes:
      - app_storage:/app/storage
    expose:
      - "8501"
    networks:
      - internal
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 40s
    security_opt:
      - no-new-privileges:true
  cloudflared:
    image: cloudflare/cloudflared:latest # pin digest/version after successful test
    restart: unless-stopped
    command: tunnel --no-autoupdate run
    environment:
      TUNNEL_TOKEN: ${TUNNEL_TOKEN:?TUNNEL_TOKEN is required}
    depends_on:
      web:
        condition: service_healthy
    networks:
      - internal
networks:
  internal:
    driver: bridge
volumes:
  app_storage:
```

Note: `TUNNEL_TOKEN` environment variable is supported by Cloudflare for `cloudflared tunnel run`. Tunnel DNS and published application route must be configured in Cloudflare dashboard to `http://web:8501`. The `cloudflared` service has no inbound public port; only outbound connection. Compose `expose` is not `ports`. For tighter security/reproducibility lock image digests after functional test and ensure host patch updates.

### Operator deployment checklist
1. Confirm target host, repo path, Docker Engine + Compose versions and available CPU/RAM/disk; record existing service names/ports. Do not assume an unused port or host path.
2. Confirm domain active in Cloudflare account; configure managed tunnel published application `www.aihubcampus.online` → `http://web:8501`, correct DNS, SSL and suitable access policy. No wildcard or account-wide change without permission.
3. `cp .env.example .env`, insert new token/password/secret, `chmod 600 .env`. For production use long random strong admin password; if user insists on short `web:2026`, advise and require password change before public exposure.
4. `docker compose config --quiet` (care not to print expanded env), `docker compose build`, `docker compose up -d`.
5. Check `docker compose ps`, web health, cloudflared connection logs **redacted**, HTTPS domain, login, upload, plot rendering and prediction over real browser.
6. Restart stack and check persistent DB/data, active artifact and passwords; verify no accidental external port.
7. Configure periodic backup of `app_storage` including SQLite consistent snapshot + model manifest + dataset version metadata, kept outside live volume; document restore and run one restore drill (without harming production).
8. Document rollback: backup DB volume; image tag / release commit; `docker compose down` (without `-v`), restore last image and checked model package; database schema migrations must be backwards compatible or have explicit restore procedure. Never use `docker compose down -v` in production.

### Smoke commands (run only in authorized project directory)

```bash
# Build, start, check (use operator's confirmed folder)
docker compose config --quiet
docker compose up -d --build
docker compose ps
# Safe local internal app check
docker compose exec -T web python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health').status)"
# Test live origin from an external workstation if user approved public deployment
curl -I https://www.aihubcampus.online
```

If Cloudflare shows 502/1033 or WebSocket errors: inspect cloudflared connectivity, Docker DNS/service name, route protocol, security policies and Streamlit host/XSRF config in that order. Do NOT expose :8501 publicly to bypass the tunnel.

---

## 8. Hermes → Multica execution rules

**Orchestrator: Hermes. Builder: Multica.** Spawn one narrow task at a time or parallel tasks only where their files and outputs do not conflict. Reviewer/Tester role may be a Hermes check or separate worker when helpful. Prefer 3 workstreams: Dataset/ML, App/Admin/UI, DevOps/QA. Minimize message churn and token usage; exception reports only unless blocked. Never allow Multica to self-certify completion with prose alone.

For every sprint, require:

```text
SPRINT ID:
GOAL:
OWNER:
FILES CHANGED:
COMMANDS EXECUTED:
ACCEPTANCE TESTS & RESULTS (with timestamps / command logs):
EVIDENCE PATHS:
RUBRIC ITEMS COVERED:
RISKS / BLOCKERS:
GIT COMMIT (if authorized):
STATUS: NOT STARTED | IN PROGRESS | BLOCKED | VERIFIED
```

**Quality gates:** feature tests green; unit/integration checks successful; lints/format checks pass; no leaked tokens, no fake test evidence; no prior uncommitted work overwritten; no false model score. Failed gate remains BLOCKED, not COMPLETE. If time constrained prioritize functional live prediction, RBAC, admin upload, EDA, model metrics and end-to-end testing ahead of cosmetic polishing.

**Git rules:** Work in one explicitly approved workspace and a dedicated branch; no changes to other projects or production containers; commits scoped by sprint, sensitive files excluded, no push/deploy without operator permission. Hermes may assign to Multica and verify branch artifacts. Track status in `docs/RELEASE_NOTES.md` or existing Kanban with evidence references.

---

## 9. Sprint roadmap — Sprint 0 to production release

### SPRINT 0 — Discovery, scope freeze, data/source intake
**Deliver:** inventory all 4 uploaded source documents/data; inspect repo/host only if authorized; identify conflicts between draft and actual dataset; document architecture, threat/data sensitivity model, rubric matrix, license/citation source and release gates.
- Read `Group Project 40%.md` fully; report requires **26 named components**, or explicit mapping into report chapters; presentation covers problem/dataset/ML/admin/user/results/ethics/Q&A.
- Verify CSV counts and columns with code, SHA256 and dtype summary. Confirm two docx versions are drafts, not proof of deployed system.
- Commit `README.md`, `blueprint.md`, `docs/rubric_matrix.md`, `docs/architecture.md`, `.gitignore` after approved repository setup.
**Acceptance:** documented source-of-truth precedence; exactly 23 predictors; class counts 23,364/6,636; no credentials in source; no host or DNS modified.

### SPRINT 1 — Repository, development environment, baseline container
**Deliver:** skeleton, pinned dependencies, `.env.example`, `.streamlit/config.toml`, Dockerfile, Compose, basic app entrypoint and health probe.
- Run `docker compose config --quiet` using temporary dummy local values only.
- App displays branded static login shell (no fake auth) and accessible health endpoint.
**Acceptance:** image builds, web container healthy with no `ports` mapped, local health endpoint returns 200; no Cloudflare token required during build/test (can run web alone).

### SPRINT 2 — CSV integrity, schema and version manager
**Deliver:** `ml/schema.py`, `src/validation.py`, `ml/inspect_dataset.py`, `docs/data_dictionary.md`, schema tests.
- Validate exact ordered 25 columns, ID exclusions, correct target semantics, class distributions, known legal code values and signed billing amounts.
- Upload parser makes controlled quarantine file, rejects invalid CSV, writes error reason, prevents path traversal and over-size files.
**Acceptance:** seeded CSV passes, each malformed fixture fails for expected reason; original CSV unchanged; reproducible dataset metadata checksum.

### SPRINT 3 — Preprocessing and EDA evidence
**Deliver:** preprocessing pipeline design plus 6 actual PNG/SVG EDA plots, descriptive statistical summary and plain-English interpretations in `docs/report_evidence.md`.
- Class balance bar, age/class boxplot, credit limit/class boxplot, PAY_0 default-rate plot, education default rates, selected numeric correlation heatmap.
- No untested causal assertions. Format chart title, axes, source, units; report min/max class counts.
**Acceptance:** scripts regenerate all six plots from CSV; no chart is placeholder; at least one substantive observation per plot.

### SPRINT 4 — Three-model training and fair evaluation
**Deliver:** `ml/train.py`, `ml/evaluate.py`, reproducibility files and three metrics/confusion matrices.
- Fixed stratified split 80/20 with seed saved; same target and input contracts; pipelines avoid train/test leakage.
- Train LR, max-depth-5 DT, 100-tree depth-5 RF; compare accuracy/precision/recall/F1/ROC-AUC + baseline.
- Select based on documented objective, train-only choice and test-only final evaluation. Compare v3 claims as `claimed/reference` vs `reproduced` in evidence table.
**Acceptance:** rerun on same environment gives same numerical results (within tiny floating tolerance); metrics mathematically consistent with confusion matrix totals 6,000; no placeholder scores.

### SPRINT 5 — Model artifact, prediction service, safety mapping
**Deliver:** `best_pipeline.joblib`, `metrics.json`, `model_manifest.json`, inference + recommendation tests.
- Exact feature order verified against manifest; no `joblib` loaded from untrusted uploader.
- Support invalid/missing/out-of-range field feedback; return class + model probability + tier; negative valid bills allowed.
**Acceptance:** direct CLI vs loaded pipeline outputs identical class/probability for >=5 representative synthetic inputs; threshold boundary tests (0.25/0.50/0.75) pass; result includes warning.

### SPRINT 6 — SQLite, real authentication, role guards
**Deliver:** DB migrations, password hash / verify, seeded admin creator, login/logout/session and role guard tests.
- Admin bootstrap username `web`, password from environment ONLY; do not print/store plaintext.
- Regular user cannot access admin reads/writes by URL/navigation/function calls; inactive user blocked; prevent last admin deactivation.
**Acceptance:** credential tests, wrong password, expiration/logout and role-bypass all pass; DB persists after restart; no plain SHA256 password storage.

### SPRINT 7 — User prediction UI (complete vertical slice)
**Deliver:** responsive 23-input form, default examples (synthetic), validation, result/probability/recommendation and user-owned prediction history.
- Categorized controls and help labels, no dummy risk predictions. Safe rerender; protect against accidental duplicate submissions.
**Acceptance:** authorized user enters valid features and sees exact pipeline result; invalid data blocks model invocation with readable message; browser on 375px and desktop remains usable.

### SPRINT 8 — Admin user management
**Deliver:** list/add/edit/deactivate users, role change and admin password reset interface, audit logging and tests.
- No public self-registration; appropriate password hashing; cannot orphan system without enabled admin.
**Acceptance:** admin can provision user; user logs in; admin role restricted; stored hashes not displayed; forbidden attempts denied and audited.

### SPRINT 9 — Admin dataset manager
**Deliver:** dataset metadata, preview/counts, validated upload, activate/version and rejection logs.
- Upload must not automatically retrain/replace live model; show clearly which dataset built active model. Distinguish **staged dataset** from **deployed model dataset**.
**Acceptance:** original CSV validates and can be staged; missing-column/wrong-target uploads rejected; active dataset pointer persists; model remains unchanged unless explicitly rebuilt/approved.

### SPRINT 10 — Admin model evaluation / insight panels
**Deliver:** model comparison, metrics, all 6 EDA plots, 3 confusion matrices, source/meta, limitations and date/model version.
- Use generated artifacts, not hard-coded v3 statistics. Color coding accessible; detail view for TP/TN/FP/FN.
**Acceptance:** real outputs match metrics.json exactly; charts load after restart; no broken plots; User cannot reach unauthorized management.

### SPRINT 11 — Automated testing & adversarial verification
**Deliver:** `tests/` plus `docs/test_matrix.md` with expected, observed, timestamps and evidence for 12 core tests, expanded security/integration cases.

| ID | Must demonstrate |
|---|---|
| T01 | Valid admin and user login, distinct views |
| T02 | Incorrect credentials rejected / throttled |
| T03 | User prohibited from admin screen **and underlying privileged functions** |
| T04 | Admin adds/edits user and persists change |
| T05 | Valid 25-column CSV accepted/staged with counts |
| T06 | Missing-column/malformed CSV rejected with clear reason |
| T07 | Valid 23-field submission returns genuine class/probability/advice |
| T08 | Invalid age/limit/codes/missing numeric values rejected |
| T09 | App class and probability match standalone pipeline output |
| T10 | Tier mapping and textual recommendation match score boundaries |
| T11 | Restart retains SQLite, model and protected access |
| T12 | Full user login → prediction → history → logout works |

Additional: CSRF/CORS/websocket behavior, role enforcement, file-size limit, admin deactivation, password storage, no secrets logged, inaccessible DB path, model artifact verify, upload quarantine.
**Acceptance:** all T01–T12 executed with actual recorded results; failed tests cause repair/retest, NEVER mark pass without evidence.

### SPRINT 12 — Production-like Docker hardening, recovery
**Deliver:** non-root image, minimal runtime permissions, locked dependencies, Compose health checks, backup/restore scripts, security checklist, ops runbook.
- Confirm only required writable mount, no host port exposure, scan source for secret patterns, test clean rebuild and backup restore.
**Acceptance:** fresh clone + provided CSV + `.env` builds/runs; simulated restart preserves app; verified backup/restoration in disposable environment.

### SPRINT 13 — Cloudflare Tunnel and HTTPS staging verification
**Deliver:** operator-approved Cloudflare-managed tunnel attach, public hostname `www.aihubcampus.online`, HTTPS smoke report, tunnel mapping screenshot (without token), privacy and safe browser test.
- Operator inserts token `.env`; set route `http://web:8501`; compose tunnel starts after healthy app; DNS matches intended host.
- Test Cloudflare route, HTTPS, login/session, upload, model prediction, admin, WebSocket/refresh, mobile.
**Acceptance:** actual URL works reliably over HTTPS from outside Docker host; no public origin port; secrets not shown anywhere. **Do not start Sprint 13 or modify DNS/tunnel without explicit deployment authorization.**

### SPRINT 14 — Report/rubric evidence and academic honesty
**Deliver:** `docs/report_evidence.md`, `docs/rubric_matrix.md`, genuine figures/tables/screenshots, report section draft/correction checklist aligned to all **26 required sections**.
- Align v3 wording to actual implementation; if deployment is now cloud-hosted, revise outdated 'cloud hosting future work' statements. If new password algorithm used, revise SHA256 passage. Do not claim four members or 14-day schedule are factual without group confirmation.
- Report actual model metrics, dates, test evidence, implementation differences; discuss high false negatives, historical Taiwan data, privacy, demographic bias and no automatic bank decision.
**Acceptance:** 26 report components mapped; nine report rubric categories accounted for; no 'completed' claims unsupported by screenshots/run logs.

### SPRINT 15 — Presentation, live demo and technical Q&A
**Deliver:** simple 10–12 slide outline or presentation contents, demo script and question bank; adjust time to lecturer's actual instruction (10 min is v3's draft proposal, not a confirmed assessment limit).
- Slide order: problem, objectives, dataset, preprocessing, EDA, ML models/split, comparison/confusion matrix, architecture, Admin demo, User prediction demo, ethics/limitations, conclusion/improvements.
- Practical demo: Admin login/user management/dataset validation → User login → enter preset 23 values → model probability/advice → invalid input → model evaluation → sign out.
- Each member covers part and prepares model-accuracy-vs-recall/overfitting/leakage/class imbalance/probability/role security/ethics answers.
**Acceptance:** rehearsed clean demo with working live app; screenshots/screencast evidence if permitted; actual team assignments confirmed rather than invented.

### SPRINT 16 — Production release, audit and handover
**Deliver:** tagged candidate release, deployment log, `docs/runbook.md`, `docs/RELEASE_NOTES.md`, final compliance matrix, operational backup/rollback evidence.
- Confirm explicit approval for go-live and release checklist. Snapshot DB; deploy pinned image/model; run all smoke tests; monitor startup and errors; rotate exposed trial token.
- Owner receives operational commands, secret input list, health/backup steps, reproducibility procedure and deployment URL.
**Acceptance:** all rubric-critical functions verified; live HTTPS end-to-end passes; no unresolved critical risk; latest backup and rollback tested; release marked COMPLETE only with attached evidence.

### Sprint dependencies & parallelism

```text
S0 -> S1 -> S2 -> S3 -> S4 -> S5
           \-> S6 -> S8 -> S9
                    \-> S7 (needs S5 & S6)
S3 + S4 + S5 + S7 + S8 + S9 -> S10 -> S11 -> S12 -> S13
S0 + actual S3-S13 evidence -> S14 -> S15 -> S16
```

App layout/auth may be developed while ML team trains, but functional inference integration **must** depend on verified Sprint 5 model. Release and report must reflect actual implementation; no pretending progress.

---

## 10. Official rubric coverage matrix

### Report (20 marks)

| Rubric item | Marks | Required evidence / primary sprints |
|---|---:|---|
| Problem, objectives, scope | 2 | S0, S14 report problem and SMART objectives |
| Dataset selection, description, preprocessing | 3 | S2–S3 source/25 columns and cleaning decisions |
| EDA and interpretation | 2 | S3 six real charts + meaningful interpretation |
| Methodology/model development | 3 | S4 training, features, reproducibility |
| Model testing/evaluation | 3 | S4–S5 metrics, confusion matrices, model comparison |
| System design/model integration | 2 | S1, S5–S10, S14 architectural evidence |
| Results/challenges/ethics | 2 | S11, S14 observed limitations and ethical analysis |
| Conclusion/future enhancements | 1 | S14 credible evidence-backed conclusion |
| Structure/citations/professional quality | 2 | S14 references, captions, organization |
| **TOTAL** | **20** | |

### Presentation & demonstration (20 marks)

| Rubric item | Marks | Required evidence / primary sprints |
|---|---:|---|
| Problem and objectives | 2 | S15 opener |
| Dataset, preprocessing, EDA | 2 | S2–S3, S15 |
| ML methods and performance | 3 | S4, S10, S15 |
| Admin module demo | 2 | S8–S9, S15 |
| User prediction demo | 3 | S5, S7, S15 |
| Overall integration | 3 | S11–S13 public working system |
| Presentation quality | 2 | S15 clean slides and rehearsal |
| Team participation | 1 | S15 verified group roles, actual participation |
| Q&A technical understanding | 2 | S15 group drill and answers |
| **TOTAL** | **20** | |

### Report's 26 mandatory components — mapping

| # | Required section | Evidence / report module |
|---|---|---|
| 1 | Cover Page | Project name, members, course, date |
| 2 | Executive Summary | scope, dataset, real results, working demo |
| 3 | Introduction | background/problem |
| 4 | Problem Statement | bank default risk challenge |
| 5 | Objectives | measurable dataset/model/system/test outcomes |
| 6 | Project Scope | binary prediction, no automated decisions |
| 7 | Dataset Description | CSV provenance, 25 columns, target/classes |
| 8 | Data Preprocessing | split, features, no leakage, scaling |
| 9 | Exploratory Data Analysis | six labeled real plots with interpretation |
| 10 | ML Methodology | algorithms, design, split controls |
| 11 | Model Training | settings/seeds/pipeline |
| 12 | Model Evaluation | confusion matrices and metrics |
| 13 | Model Comparison | same held-out test, rationale |
| 14 | System Architecture and Design | diagram/Compose/DB/roles |
| 15 | Admin Module | screenshots plus management/test evidence |
| 16 | User Module | end-to-end user workflow |
| 17 | Predictive Model Integration | `joblib`/input schema/version mapping |
| 18 | System Testing | real T01–T12 results |
| 19 | Results and Discussion | quantitative output/limitations/errors |
| 20 | Ethical and Privacy Considerations | finance/privacy/demographic/bias issues |
| 21 | Challenges and Solutions | actual obstacles + concrete fixes |
| 22 | Limitations | recall, time/context/generalization |
| 23 | Future Enhancements | improved recall/calibration/local data |
| 24 | Conclusion | no unsupported success claims |
| 25 | References | UCI/Yeh & Lien/scikit-learn/Streamlit/docs |
| 26 | Appendices | dataset schema, configuration, tests, code links |

Grouping these under fewer broad chapters is acceptable ONLY if all 26 are explicitly findable via headings or cross-reference map and lecturer instructions permit it.

---

## 11. Acceptance commands and objective evidence

Examples of expected commands in authorized repository:

```bash
python -m ml.inspect_dataset --csv data/UCI_Credit_Card.csv
python -m ml.generate_eda --csv data/UCI_Credit_Card.csv --out models/eda
python -m ml.train --csv data/UCI_Credit_Card.csv --out models
python -m ml.evaluate --models-dir models
python -m ml.verify_artifact --models-dir models
python -m pytest -q
python -m compileall -q app.py src ml
# after user provides .env locally:
docker compose config --quiet
docker compose build
docker compose up -d
# test app internal health:
docker compose exec -T web python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health').status)"
```

These are **contractual interfaces to implement** (not statements they currently exist). Capture stdout/test counts into `evidence/test-results/`, redact env/credentials. Confirm that instructions are portable to Fedora/Linux with Docker Compose plugin. A `README.md` quickstart must list reliable install steps, initial account provisioning, expected model input units, troubleshooting and safe teardown.

### Release gates
- **Gate A: Academic Data** — correct source/counts/classes/features, six EDA figures, descriptive interpretations.
- **Gate B: ML** — 3 trained real algorithms, held-out metrics, comparisons, confusion matrices, selected real artifact, no leakage and documented low recall.
- **Gate C: App** — genuine RBAC, Admin+User, all 23 inputs, probability, advice, CSV manager, predictive output directly from artifact.
- **Gate D: Quality** — 12 test cases evidenced, critical permission tests and edge cases, restart/data persistence, no leaked credentials.
- **Gate E: Public Release** — explicit permission, Cloudflare hostname and route correct, HTTPS live demo, no host port, reproducible backup+rollback.
- **Gate F: Submission** — 26 report components, 9+9 rubric items, presentation/script/Q&A, zero unverifiable 'PASS' statements.

**STOP condition:** fail release if any critical security bypass, unknown model source, mismatched feature order, fabricated metric/test, broken production tunnel or inability to restore/rollback.

---

## 12. Academic caveats and controlled deviations from v3

1. Draft v3 claims Streamlit + SQLite implementation, 12 PASS tests, 14-day completion, 4 group members and numeric scores. This blueprint treats those as **draft claims awaiting runtime evidence**, not facts proven by an uploaded report.
2. v3's password hashing mentions basic SHA-256. Implement modern Argon2id/bcrypt and update report to reflect final actual implementation.
3. v3 class labels sometimes imply 'On Time' certainty; phrase outputs as model-predicted **default/non-default next month**, with actual behavior uncertain.
4. v3 calls cloud hosting a future enhancement, but user explicitly requests live Cloudflare deployment. Correct **actual** report system architecture/scope and keep future work focused on robust enterprise databases, monitoring, retraining and better recall.
5. v3 provides 4 risk tiers from model probabilities. Preserve four bands as an educational mapping, explicitly **not calibrated regulatory banking risk grades**; use human review, not automatic credit punishment.
6. v3 has very low positive recall. Do not conceal it or optimize only for accuracy. Discuss tradeoffs and possible train/validation-only future improvements, e.g. class weights, threshold tuning, calibration, SMOTE inside CV folds.
7. v3 references 10-minute live demo and 14-day plan. Treat as planning assumptions; confirm actual lecturer deadline/presentation duration and true group contributions before reporting these as factual.
8. UCI data relates to Taiwan's 2005 credit-card borrowers and NTD. Do not imply Malaysian customers, Malaysian Ringgit, new/live bank data or applicability to current local populations.
9. A containerized public academic demo is **production-like engineering**, not independently certified as safe for real-world lending; state this boundary.

---

## 13. Handover instructions to Hermes — copy these as the mission

> Implement the attached `blueprint.md` for AI Hub Campus credit-card default prediction. The assessment authority is `Group Project 40%.md`; refer to detailed draft v3 and use the supplied `UCI_Credit_Card.csv`. Work sequentially through Sprint 0–16 and report only VERIFIED sprints with concrete evidence, test commands/results and file paths. Delegate bounded builder tasks to Multica when beneficial, and independently verify claims. Keep Streamlit/scikit-learn/SQLite/Docker/Cloudflare implementation simple. Admin and User must both function; 23 input attributes, legitimate saved trained model, metrics, probability and recommendations are mandatory. Preserve 3-model comparison and 6 real EDA charts. Initial admin username `web`; admin password and tunnel token come ONLY from operator-managed `.env`, never source. Public domain is `www.aihubcampus.online`; Cloudflare Tunnel routes to `http://web:8501` over internal Docker network. Do not edit other projects, expose public ports, touch any existing production environment or change Cloudflare DNS/tunnels until operator authorizes deployment. Report failures honestly, do not fake PASS/metrics, and provide a complete rubric crosswalk, runbook, testing artifacts and academic presentation notes. Do not claim the project finished merely because code or Compose files exist.

---

## 14. Official reference starting points

- Assignment authority: supplied `Group Project 40%.md`.
- Source academic draft: supplied `Credit_Card_Default_Prediction_Project-v3.docx`.
- Earlier draft: supplied `Credit_Card_Default_Prediction_Project.docx`.
- Local dataset: supplied `UCI_Credit_Card.csv`.
- UCI ML Repository, *Default of Credit Card Clients*: https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients
- Yeh, I.-C. & Lien, C.-H. (2009), *The comparisons of data mining techniques for the predictive accuracy of probability of default of credit card clients*, Expert Systems with Applications 36(2), 2473–2480.
- scikit-learn Pipeline: https://scikit-learn.org/stable/modules/compose.html#pipeline
- Streamlit deployment/config: https://docs.streamlit.io/develop/api-reference/configuration/config.toml
- Cloudflare managed tunnels: https://developers.cloudflare.com/tunnel/get-started/
- Cloudflare `TUNNEL_TOKEN` environment parameter: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/configure-tunnels/run-parameters/

**Final operating principle:** a modest, reproducible, working ML app with truthful evidence scores higher on this rubric than a large-looking, partly simulated system.
