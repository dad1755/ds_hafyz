# 14. System Architecture and Design

Draft, Sprint 14. The design record is `docs/architecture.md`; the runtime facts are observed in
`evidence/s13/` and `evidence/s12/`.

## 14.1 Topology

```text
Browser --HTTPS--> Cloudflare edge --> remotely-managed tunnel (outbound only)
        --> cloudflared container --internal network--> web:2026 (Streamlit)
        --> session/RBAC guard + 23-field validation
        --> cached joblib Pipeline (fixed feature order) --> class + predict_proba
        --> tier/recommendation mapping --> SQLite (users, sessions, dataset_versions,
            prediction_logs, audit_events, login_attempts, schema_migrations)
```

Two containers in one compose project, `aihubcampus`, on one internal bridge network. `web` exposes
2026 inside the network and publishes nothing. `cloudflared` publishes nothing and dials out. The
only ingress is the operator's existing tunnel, whose configured target is `http://web:2026`.

The port is 2026 rather than the blueprint's 8501 because the operator's ingress already pointed at
2026; the design treats the ingress as immutable and adapts the application, and the deviation is
recorded as D1 in `docs/architecture.md` §9.

## 14.2 Components

| Component | Path | Responsibility |
|---|---|---|
| Entry point and dispatch | `app.py` | Resolves the session from the database on every rerun; renders sign-in, forced password change, or one role-aware page |
| Config | `src/config.py` | Typed environment settings; no defaults for secrets |
| Database | `src/db.py` | SQLite connection policy (WAL, 5 s busy timeout, foreign keys on), idempotent migrations |
| Security | `src/security.py` | Argon2id hashing, server-side sessions, RBAC guard, login throttling |
| Accounts API | `src/accounts.py` | Admin operations; each calls `require_role` first |
| Validation | `src/validation.py` | 25-column CSV contract and the 23-feature request contract |
| Inference | `src/inference.py` | Verifies then loads the pipeline once; `predict` validates first |
| Recommendations | `src/recommendations.py` | Deterministic band → advice mapping |
| Dataset manager | `src/data_manager.py` | Quarantine, checksum, version, activation; never trains |
| Evaluation panel | `src/evaluation.py`, `src/pages_evaluation.py`, `src/charts.py` | Renders the recorded metrics and figures; owns no statistic |
| Pages | `src/pages_login.py`, `src/pages_prediction.py`, `src/pages_history.py`, `src/pages_admin.py`, `src/pages_datasets.py` | One module per screen, each re-checks the session |
| ML scripts | `ml/*.py` | Inspect, EDA, train, evaluate, verify artifact — offline only |

## 14.3 Storage

SQLite at `/app/storage/aihubcampus.db` on the named volume `app_storage`. Eight tables:
`users`, `sessions`, `login_attempts`, `prediction_logs`, `dataset_versions`, `dataset_rejections`,
`audit_events`, `schema_migrations`. Two deliberate choices are worth naming:

- **`prediction_logs` stores no feature snapshot.** A row records the class, probability, band,
  model version and timestamp for a user id — not the 23 inputs. That limits what a database leak
  would expose and is why the history page says a row is a model output, not a record about a
  customer.
- **`sessions.token_hash` is the SHA-256 of the bearer token**, so the table cannot be replayed as a
  credential. Sessions have an absolute 8-hour expiry and a revocation timestamp.

## 14.4 Security architecture

The controls that matter, each verified by a test or a live probe rather than by inspection:

| Control | Implementation | Verified by |
|---|---|---|
| Password hashing | Argon2id (`m=65536, t=3, p=4`, 16-byte random salt), constant-time verify, no SHA-256 path | `evidence/s6/security_smoke.txt` |
| Role enforcement | `require_role` re-reads the user row inside every privileged function | T03, 14-function sweep in `docs/test_matrix.md` |
| Session authority | Server-side session row; `session_state` is never the sole authority | T11, `evidence/s11/restart.txt` |
| Brute force | 5 failures in 15 minutes locks the username for 15 minutes, expiring by itself | T02 |
| Upload safety | 10 MiB cap, extension/MIME/parse/schema validation, generated quarantine filename, never executed | adversarial rows in `docs/test_matrix.md` |
| Artifact trust | 11 ordered checks including checksum and a pickle class allowlist before deserialisation | `docs/inference_contract.md` §2 |
| Container | read-only rootfs, `cap_drop: ALL`, `no-new-privileges`, non-root `app`, digest-pinned base | `evidence/s12/smoke_test.txt` |
| Ingress | no published host port; tunnel only | `evidence/s13/smoke_test.txt` |

## 14.5 Deviations from the blueprint

Fourteen deviations are recorded with their reasons in `docs/architecture.md` §9 — the port, the
hash algorithm, the absent `PAY_1`, the scientific-notation handling, the subnet, the tunnel token
source, the validation boundaries, the extra `ml/` copy, the two extra tables, the password policy
and the `scripts/` copy. The pattern is consistent: where the blueprint and the running system
disagreed, the system's behaviour was recorded rather than the blueprint being quietly edited.

## Evidence

- `docs/architecture.md`
- `compose.yaml`
- `Dockerfile`
- `src/security.py`
- `src/db.py`
- `src/inference.py`
- `evidence/s6/security_smoke.txt`
- `evidence/s11/restart.txt`
- `evidence/s12/smoke_test.txt`
- `evidence/s13/smoke_test.txt`
- `docs/inference_contract.md`
- `docs/test_matrix.md`
