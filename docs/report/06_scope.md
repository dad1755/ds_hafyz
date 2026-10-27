# 6. Project Scope

Draft, Sprint 14.

## 6.1 In scope

- One binary classification task: next-month credit-card default, from 23 documented features.
- One public dataset, used unmodified, cited, with its checksum recorded.
- A reproducible ML pipeline: validation → EDA → stratified split → three candidate pipelines →
  held-out evaluation → one selected artifact with a manifest and a checksum.
- A single-instance web application with two roles, authentication, server-side sessions and
  audit events.
- User functions: sign in, submit the 23 features, receive class, probability, band, advice and
  disclosures, view the account's own history, sign out.
- Admin functions: list, create, edit, reset password, deactivate and reactivate accounts; stage,
  validate, reject and activate dataset versions; view the real evaluation evidence.
- A hardened container: digest-pinned base, non-root user, read-only root filesystem, dropped
  capabilities, no published host port, one writable volume.
- Public HTTPS publication through the operator's existing Cloudflare Tunnel.
- Evidence for every claim: transcripts under `evidence/`, an independent acceptance record per
  sprint under `docs/acceptance/`.

## 6.2 Out of scope, and why

The exclusion list is binding — it was fixed in the design (`docs/architecture.md` §8) and is
restated here because scope creep is the most common way a student project fails to finish:

| Excluded | Reason |
|---|---|
| Automated lending or credit-limit decisions | The system informs a human; it must not act. Stated on every result. |
| Real customer data | No personal or banking data is collected beyond a username; the form is for synthetic demonstrator values. |
| Registration, email, password reset by email | Needs an email provider and a token flow; not required by the brief. |
| Multi-tenant hosting, horizontal scaling | One instance and one SQLite file by design; a school demonstration does not need more. |
| Next.js / React front end | The brief forbids a JavaScript SPA stack for this project; Streamlit is Python-native. |
| A separate FastAPI backend | A second service would double the deployment surface for no marked benefit. |
| PostgreSQL, Redis, Celery, Kubernetes | Operational weight with no requirement behind it. |
| LLM or paid ML APIs | The task is classical tabular classification; a paid dependency would make the result unreproducible. |
| Training during a prediction request | Inference must be deterministic and fast; training is an offline script. |
| Uploading a pickled model | A pickle upload is a code-execution path; the artifact is built only by this repository's code. |
| Published host ports | The tunnel is the only ingress; a host port would bypass the edge. |
| DNS or tunnel reconfiguration by this project | The ingress already exists and belongs to the operator. |
| Fairness certification | Not achievable within the project; discussed as a limitation instead (§20.3, §22.4). |

## 6.3 Boundaries of the claim

The system is a **production-like academic prototype**. It is containerised, hardened, publicly
reachable and tested, which is more than a notebook; it is not certified, audited, load-tested
beyond a single instance, or approved for any real lending use. "Deployed" in this report means
"reachable at a public hostname and verified there", not "approved for production use".

## Evidence

- `docs/architecture.md`
- `docs/deployment.md`
- `docs/runbook.md`
- `evidence/s13/browser_check.txt`
- `docs/rubric_matrix.md`
