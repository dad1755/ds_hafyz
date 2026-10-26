# Architecture — AI Hub Campus credit card default risk prediction

Status: **design frozen in Sprint 0**; **Sprint 1 adds the container skeleton** (§11) —
a branded shell and a health probe, with no authentication, database or model. Anything
here describing behaviour beyond that is a specification, not a claim that it runs.
Deviations from `blueprint.md` are recorded in §9.

## 1. Purpose and boundary

A single-instance academic decision-support web application. A signed-in user submits
23 historical attributes of a credit-card account and receives a binary next-month
default prediction, an uncalibrated model probability, a display tier and supportive
recommendations. Admins manage users, dataset versions and view the real ML evidence.

Explicitly **not** in scope: automated lending decisions, credit scoring, customer
contact, real customer data, registration, email, multi-tenant hosting. Historical
Taiwanese 2005 data, amounts in **NTD**, no claim of fitness for current Malaysian
lending.

## 2. Runtime topology

```mermaid
flowchart TB
    subgraph client["Client"]
        B["Browser<br/>www.aihubcampus.online<br/>aihubcampus.online"]
    end

    subgraph cf["Cloudflare (operator-managed, not modified by this project)"]
        E["Edge TLS / WAF"]
        T["Remotely-managed Tunnel<br/>ingress: *aihubcampus.online → http://web:2026"]
    end

    subgraph docker["Docker Compose project: aihubcampus (internal bridge network)"]
        C["cloudflared<br/>outbound only, no published ports"]
        subgraph web["service: web"]
            S["Streamlit app :2026<br/>app.py → page dispatch"]
            A["auth + RBAC<br/>src/security.py"]
            V["validation<br/>src/validation.py"]
            I["inference<br/>src/inference.py<br/>cached joblib pipeline"]
            D["SQLite<br/>/app/storage/aihubcampus.db"]
        end
        VOL[("named volume<br/>app_storage")]
    end

    ART["models/best_pipeline.joblib<br/>metrics.json<br/>model_manifest.json<br/>(read-only in image)"]

    B --> E --> T --> C --> S
    S --> A --> D
    S --> V --> I --> ART
    S --> D
    D --- VOL
```

Text form (for reviewers without a Mermaid renderer):

```text
Browser --HTTPS--> Cloudflare edge --> remotely-managed tunnel (outbound only)
        --> cloudflared container --internal network--> web:2026 (Streamlit)
        --> session/RBAC guard + 23-field validation
        --> cached joblib Pipeline (fixed feature order) --> class + predict_proba
        --> tier/recommendation mapping --> SQLite (users, dataset_versions,
            prediction_logs, audit_events, schema_migrations)
```

Offline / reproducible ML path (no runtime training):

```text
data/UCI_Credit_Card.csv --validate(S2)--> EDA(S3) --> stratified 80/20 split(S4)
  --> 3 pipelines (LR, DT depth 5, RF 100×depth 5) --> held-out evaluation(S4)
  --> selected artifact + metrics.json + manifest(S5) --> app loads read-only(S5+)
```

## 3. Components and responsibilities

| Component | Path | Responsibility | Sprint |
|---|---|---|---|
| Entry point / dispatch | `app.py` | Navigation, session check on every route | S1/S6 |
| Config | `src/config.py` | Typed env settings, no defaults for secrets | S1 |
| DB layer | `src/db.py` | SQLite connection, WAL, idempotent migrations | S6 |
| Security | `src/security.py` | Argon2id/bcrypt hashing, session, RBAC, login throttling | S6 |
| Validation | `src/validation.py` | 23-field contract, CSV schema/ranges | S2/S5 |
| Inference | `src/inference.py` | Load manifest-verified pipeline once, predict | S5 |
| Recommendations | `src/recommendations.py` | Deterministic tier → advice mapping | S5 |
| Dataset manager | `src/data_manager.py` | Quarantine, checksum, version, activate | S9 |
| Charts | `src/charts.py` | Render saved EDA/performance figures | S10 |
| Audit | `src/audit.py` | Append non-sensitive admin events | S8 |
| ML scripts | `ml/*.py` | Inspect, EDA, train, evaluate, verify artifact | S0/S2–S5 |

Single instance of app + SQLite by design: avoids concurrent-session ambiguity on a
school demo. No horizontal scaling, no external queue, no second datastore.

## 4. Technology choices

| Layer | Choice | Why | Rejected |
|---|---|---|---|
| Runtime | Python 3.12 (pinned base image) | Streamlit/scikit-learn support, reproducible | Node/Next.js (no-go) |
| UI | Streamlit, pinned release | Fast multipage academic UI, Python-native | React SPA, FastAPI split backend (no-go) |
| ML | scikit-learn `Pipeline`, joblib | Leakage-safe preprocessing, single artifact | TensorFlow/LLM/paid APIs (no-go) |
| Data/EDA | pandas, NumPy, matplotlib | Standard, regenerable plots | Notebook-only deliverable (brief §10 forbids) |
| Storage | SQLite on a named volume | Zero-ops, sufficient for one instance | PostgreSQL, Redis (no-go) |
| Auth | `argon2-cffi` (bcrypt fallback) | Modern hashing, constant-time verify | Bare SHA-256 (prohibited by blueprint §12.2) |
| Tests | pytest + Streamlit `AppTest` | Objective gates, runnable in CI | Manual-only verification |
| Deploy | Docker Compose + `cloudflare/cloudflared` | Reproducible, no public port | Kubernetes (no-go), host port exposure (no-go) |

Exact pins land in `requirements.txt` at S1; this table records intent only.

## 5. Ingress resolution — the port 2026 decision

**The fact.** The operator's Cloudflare tunnel already publishes **both**
`www.aihubcampus.online` and `aihubcampus.online` to **`http://web:2026`**. `blueprint.md`
§2/§7 instead specify `http://web:8501`, and its compose file, healthcheck and Dockerfile
command hard-code 8501.

Provenance: operator report on issue RIDEGAMI-798, repeated in the operator's own record
(`PROJECT_DETAILS.md`, git-ignored): both hostnames → `http://web:2026`, default 404. It is
**not independently verified in S0** — the tunnel is remotely-managed, no local ingress
config exists (`~/.cloudflared` is empty), and inspecting it would need Cloudflare API
credentials.
S0 therefore treats the ingress as immutable and unverified, and S13 confirms it against
the live domain.

**Options considered.**

| Option | What it needs | Verdict |
|---|---|---|
| A. Serve Streamlit on **2026** | App port changed in one place; no Cloudflare change | **Chosen** |
| B. Keep 8501, edit the tunnel route to `http://web:8501` | Cloudflare dashboard/DNS change | Rejected — DNS/tunnel modification is out of scope and unauthorised |
| C. Keep 8501, add a proxy container mapping `web:2026 → web:8501` | An extra container and a second failure point | Rejected — complexity for no benefit |

**Decision (A).** The application serves on **2026**:

- `APP_PORT=2026` is the single source of truth; `.streamlit/config.toml`
  (`server.port`), the Dockerfile `CMD`, `EXPOSE`, the compose `expose:` entry and the
  healthcheck URL all derive from it. Reconciling to 8501 at S13, if the observed ingress
  turns out to be 8501, is a one-value change in `.env`, not a refactor.
- The compose **service name stays `web`** because the ingress target is the Docker DNS
  name `web`. Renaming it would break the route.
- `expose: 2026` only. **No `ports:` section** — no public host port, ever.
- The healthcheck hits `http://127.0.0.1:2026/_stcore/health`.

**Apex and www.** Both hostnames reach the same service, so the app must not assume one
canonical host:

- Do **not** pin `browser.serverAddress`; Streamlit derives it from the request `Host`
  header, which keeps XSRF/CORS origin checks correct for whichever name is used.
  *(Superseded in S1 — see the amendment at the end of this section: the S1 card requires
  the pin, and both hostnames were re-verified as reachable with it in place.)*
- No apex→www redirect is needed or configured (Cloudflare already routes both).
- S13 must test login, upload and a prediction over **both** hostnames.

**Risk if the report is wrong.** If the real route is `8501`, the symptom is a 502/1033
at the edge while the container is healthy. S13 detects it in one curl; the fix is the
`APP_PORT` value. Nothing else in the design depends on the number.

**S1 amendment — `browser.serverAddress` / `browser.serverPort` are pinned.** The S1 card
requires `browser.serverAddress=www.aihubcampus.online` and `browser.serverPort=443` in
`.streamlit/config.toml` (blueprint §2 asks for them "if required for proxy support"), so
they are set. They change only the URL Streamlit *reports* (`docker compose logs web` shows
`URL: http://www.aihubcampus.online:443`); where the socket binds is still `server.address`,
and S1 verified below that both hostnames still reach the app.

```text
GET http://web:2026/_stcore/health                        -> 200 ok
GET http://web:2026/ with Host: www.aihubcampus.online    -> 200
GET http://web:2026/ with Host: aihubcampus.online        -> 200
```

Both hostnames therefore still reach the app with the values pinned
(`evidence/s1/ingress_target.txt`). S13 must re-test login, upload and a prediction over
both hostnames in a real browser; if the apex turns out to be affected there, deleting the
two `[browser]` keys is the whole fix.

## 6. Data flow and storage

- `users(id, username UNIQUE, display_name, password_hash, role CHECK(admin|user),
  is_active, created_at, updated_at, last_login_at)`
- `prediction_logs(id, user_id, predicted_class, default_probability, risk_tier,
  model_version, created_at)` — **no raw feature snapshot** by default; history is
  pseudonymous by user ID.
- `dataset_versions(id, original_filename_safe, sha256 UNIQUE, record_count,
  column_count, class_zero, class_one, validated_at, activated_at, is_active,
  uploaded_by, status)` — exactly one active row, enforced in a transaction.
- `audit_events(id, actor_user_id, action, entity_type, entity_id, created_at,
  non_sensitive_details)`
- `schema_migrations(version, applied_at)`
- DB at `/app/storage/aihubcampus.db` on the `app_storage` volume; WAL + busy timeout.
- Model artifacts are baked read-only; the app never writes `models/`.

## 7. Data sensitivity and threat model

**Assets.** Operator credentials (admin password, session secret, tunnel token) ·
password hashes · prediction logs · dataset versions · the model artifact · the SQLite
file · the Cloudflare tunnel identity.

**Data sensitivity.** The benchmark dataset is public, aggregated, 2005-era and
**pseudonymous** — `ID` is a sequential index, not a customer identifier. That lowers
dataset risk but not system risk: the app stores credentials and behavioural logs. No
real customer record may ever be entered into the form; demo rows are synthetic and
labelled.

**Actors.** Anonymous internet user · authenticated User · Admin · operator (host +
Cloudflare) · the model artifact supply chain.

| # | Threat | Vector | Control | Residual |
|---:|---|---|---|---|
| T1 | Credential stuffing / brute force on login | Public login form | Argon2id hashes, constant-time verify, SQLite-backed attempt counter with expiry, generic error text | No MFA (out of scope); rate limit is per-instance |
| T2 | Privilege escalation User → Admin | Direct URL / forged session state | Server-side session + role check inside **every** privileged function, not just navigation; `Streamlit` session state is never the sole authority | None accepted; verified by T03 |
| T3 | Session hijack | Cookie theft over shared device | Signed session, expiry, logout invalidation, `enableXsrfProtection=true`, HTTPS only via tunnel | No device binding |
| T4 | Secret disclosure | Logs, `docker inspect`, git, screenshots | Secrets only in operator `.env` (mode 600, git-ignored); never logged or echoed; redaction in evidence; `git grep` gate | Host root can read env — accepted, host is single-tenant |
| T5 | Malicious CSV upload | Admin dataset upload | Size cap (10 MB), extension + MIME + **parse/schema** validation, quarantine path with generated filename, never executed, never auto-retrains | Admin is trusted; upload is still non-executable |
| T6 | Untrusted model artifact | Replacing `joblib` | Artifacts built only by trusted repo code; manifest + checksum verified at load; no upload path for pickles | Supply-chain risk in pinned packages |
| T7 | SQL injection | Any DB access | Parameterised queries only | — |
| T8 | Public origin exposure | Direct port access bypassing Cloudflare | `expose:` only, no `ports:`; single internal network; no host bind | Host-level firewall is the operator's control |
| T9 | Data exfiltration via prediction history | User reads others' rows | Queries filtered by session user ID server-side; admin sees aggregates, not raw features | Admin is trusted by design |
| T10 | Unfair or harmful output | Demographic features driving advice | Outputs framed as supportive, human-review-first; demographic ablation discussed in the report; no automated adverse action; disclaimer on every result | Fairness is **not** proven — must be stated as a limitation |
| T11 | Log leakage of sensitive input | Debug logging of 23 features | Never log submissions, credentials, hashes, cookies or tokens; 30-day retention default | — |
| T12 | Denial of service / cost | Public form abuse | Cloudflare edge protection; single instance is intentionally not HA | Availability is best-effort for an academic demo |

**Compliance stance.** No personal data is collected from users beyond a username;
no identity or banking account data is requested. The dataset is public and cited. The
system is a teaching artefact, not a regulated credit-decision system, and says so on
every screen.

## 8. Scope exclusions (binding)

No Next.js/React, no separate FastAPI backend, no PostgreSQL, no Redis, no Kubernetes,
no Celery, no LLM, no paid ML APIs, no registration/email, no training during a
prediction request, no `pickle`/`joblib` uploads, no public host port, no DNS or tunnel
change by this project, no writes outside `/home/ec-user/non_prod/hafyz_ds`, no Docker
project other than `aihubcampus`.

## 9. Deviations from `blueprint.md` (recorded as required by §3)

| # | Blueprint says | This project does | Why |
|---:|---|---|---|
| D1 | App on `:8501`, healthcheck on 8501 | `APP_PORT=2026` everywhere | Observed ingress targets `web:2026` (§5) |
| D2 | Password hashing "argon2-cffi **or** bcrypt" | Argon2id via `argon2-cffi` | One algorithm, one code path, easier to test |
| D3 | `PAY_1` implied by "six status columns" naming | `PAY_0, PAY_2…PAY_6` exactly as the CSV | The dataset has no `PAY_1`; inventing one would break the contract |
| D4 | Dataset described as all-integer monetary columns | Monetary columns read as float-safe, whole-NTD values | 4,262 cells use scientific notation (see `docs/report_evidence.md`) |
| D5 | Six EDA plots as a fixed list | Same six; captions must state the actual observed numbers | Draft's education "others" figure was wrong (C7) |
| D6 | §2: pin `browser.serverAddress`/`serverPort` only "if required" | Pinned to `www.aihubcampus.online` / `443` | Required by the S1 card; both hostnames re-verified reachable with the pin (§5 amendment) |
| D7 | §7 compose: `networks: internal: driver: bridge` | Same, plus `ipam` subnet `10.202.0.0/24` | The host daemon's predefined address pools are exhausted, so an implicitly-subnetted network cannot be created (§11) |
| D8 | §7 compose: `cloudflared` reads `${TUNNEL_TOKEN:?}` | `cloudflared` reads `.env.cloudflared` via `env_file` with `required: false` | `${TUNNEL_TOKEN:?}` makes `docker compose config` fail when the token is absent; the app must build and run without any Cloudflare credential (§11) |

## 10. Open decisions deferred to later sprints

- ~~Exact Streamlit/sklearn pins (S1)~~ — resolved in S1: `requirements.in` (direct) →
  `requirements.txt` (fully pinned lock, 54 entries) on Python 3.12; see §11.
- Whether the optional `127.0.0.1:2026` troubleshooting bind is enabled (S12, off by default).
- Model selection if reproduction differs from the draft's Decision Tree (S4) — decided on
  F1 and default-class recall, never accuracy alone.
- Backup/restore drill mechanics (S12).

## 11. S1 implementation record — container skeleton

**What exists now.** `app.py` renders the branded shell and an inert sign-in form;
`src/config.py` is the typed, non-secret settings loader; `Dockerfile`, `compose.yaml`,
`.streamlit/config.toml`, `.env.example`, `.env.cloudflared.example` and `.dockerignore`
define the runtime. There is still no authentication, no database, no model and no dataset
in the image.

**Container facts, each captured in `evidence/s1/`.**

| Fact | Value | Evidence |
|---|---|---|
| Base image | `python:3.12-slim`, Python 3.12.14 | `image_contents.txt` |
| Runtime user | `app` (uid/gid 1001), non-root | `health_inside.txt` |
| Listening port | `2026` (`EXPOSE 2026`, `expose: 2026`, no `ports:`) | `image.txt`, `compose_config.txt` |
| Host port mapping | none — `docker port` empty, `NetworkSettings.Ports = {"2026/tcp":null}` | `no_host_port.txt` |
| Health | `/_stcore/health` → `200 ok` from inside the container and from a peer container on the network | `health_inside.txt`, `ingress_target.txt` |
| Image contents | `/app` = `.streamlit`, `app.py`, `requirements.txt`, `src/`, `storage`; no `.env`, no `.db`, no dataset | `image_contents.txt` |
| Tests | 11 passed (settings + shell) | `pytest.txt` |
| Clean checkout | `git archive` of the branch into an empty dir → `docker build --no-cache` succeeded (5m30s), `compose config --quiet` exit 0, 11 tests pass | `clean_checkout.txt` |
| Shell behaviour | submitting the form produces a warning only: 0 success, 0 error, no credential echoed | `apptest.txt` |

**Host constraint — the pinned subnet (D7).** On `ridergami2` the Docker daemon's predefined
address pools are fully subnetted by the other ~40 networks on the host, so creating the
project network implicitly fails:

```text
$ docker network create aihubcampus-s1-probe
Error response from daemon: all predefined address pools have been fully subnetted
exit=1
```

`compose.yaml` therefore pins `10.202.0.0/24` for `internal`. The range sits outside the
daemon's default pools (`172.16.0.0/12`, `192.168.0.0/16`), so it cannot be handed to a
later stack, and it overlapped none of the host's other networks — the check records
`overlaps=0` in `evidence/s1/network_constraint.txt`. This is a project-local compose
setting; no daemon configuration was touched. If the host is ever re-subnetted, the value
is one line.

**Tunnel token handling (D8).** `cloudflared` gets `TUNNEL_TOKEN` from `.env.cloudflared`
through an `env_file` entry marked `required: false`. Consequences: `docker compose config
--quiet` and `docker compose up -d web` work on a host with no Cloudflare credential at all,
and the token never enters compose interpolation (so it cannot leak into `docker compose
config` output, which is only ever run with `--quiet`). The service stays named `web`
because the ingress targets that DNS name, and `cloudflared` was deliberately **not started**
in S1 — starting the tunnel is S13's job.

**Not done in S1, by design.** No authentication, no RBAC, no SQLite, no dataset versioning,
no model, no EDA, no tunnel, no deployment. Nothing in this sprint answers on a public
hostname, and `docker compose down` (never `-v`) left the stack stopped at the end of the
sprint.
