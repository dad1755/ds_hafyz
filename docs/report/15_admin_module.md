# 15. Admin Module

Draft, Sprint 14. The implementation is `src/accounts.py`, `src/pages_admin.py`,
`src/data_manager.py` and `src/pages_datasets.py`; the evidence is `evidence/s8/` and
`evidence/s9/`.

## 15.1 What the administrator can do

**User management.** List accounts, create one, change a display name, change a role, reset a
password, deactivate and reactivate. There is **no delete**: `src/` contains no `delete_user` and no
`DELETE FROM users`, because deleting an account would destroy its audit history and its prediction
rows. Deactivation is the supported removal, and it revokes the account's open sessions in the same
transaction.

Every write is one audited transaction with a named action: `user.created`,
`user.display_name_changed`, `user.role_changed`, `password.reset`, `user.deactivated`,
`user.activated`. The audit detail is non-sensitive: a reset records `{"forced_change": true,
"username": …}` and never the password.

**Dataset management.** The page shows two different things side by side and refuses to conflate
them: the **deployed model dataset** (the checksum recorded in `models/model_manifest.json` — the
bytes the live artifact was trained on) and the **active dataset version** (a pointer a future
retraining run would read). When they are the same bytes the page says so; after an activation it
says in as many words that the active dataset is not the one that built the deployed model.

An upload goes: quarantine under a generated filename → schema validation → one `dataset_versions`
row with SHA-256, record and column counts, class counts and `status = validated` → aggregates shown
to the admin (counts, class balance, per-column min/max/mean/distinct). No row of data is ever
displayed. A refusal writes a `dataset_rejections` row with the reason the administrator saw and a
stable code (`missing_column`, `invalid_target_value`, …), plus an audit row, and deletes the
quarantined copy once recorded.

**Model evaluation.** The admin sees the real evaluation evidence: three candidates beside the
baseline, cross-validated mean/std, held-out scores, confusion matrices with TN/FP/FN/TP and their
shares, six EDA figures, feature importances from the deployed artifact, and the metadata (model
version, training timestamp, dataset checksum, package versions, threshold, artifact digest
recomputed on every render). The page owns no statistic: `evidence/s10/trace_metrics.txt` diffs two
independent renderings against `models/metrics.json` and reports 0 mismatches, and a test rewrites a
copy of `metrics.json` and asserts the page shows the sentinel values.

## 15.2 What protects it

The page is a view; the control is in the service. Every function in `src/accounts.py` and
`src/data_manager.py` calls `require_role(...)` before it does anything, so a user session calling
`accounts.create_user` directly gets `PermissionDenied` and an `auth.denied` audit row naming the
attempted function. This is proven by a sweep over 14 privileged entry points with a user token and
with a forged token (`docs/test_matrix.md` T03), including a guard assertion that the sweep list has
at least 14 entries and names the functions it claims to cover — so the test cannot pass by
iterating over nothing.

Two further invariants are enforced inside the write transaction, not in the UI: the last enabled
administrator cannot be demoted or deactivated, and exactly one dataset version can be active (a
partial unique index on `is_active = 1` backs the transactional clear-and-set, and a test bypasses
the code with a direct `UPDATE` to prove the index holds).

## 15.3 What the admin module does not do

- It cannot delete a user, edit a password hash, or read any hash into a page (`UserView` has no
  hash field).
- It cannot train, retrain or replace the model. Every upload and activation audit row records
  `retraining_triggered: false` and `model_replaced: false`, and the artifact's SHA-256 is identical
  before and after an upload (`evidence/s9/probe_datasets.txt`).
- It cannot see another user's prediction rows: the history query filters by the session user id
  inside the query and takes no user argument.

## Evidence

- `src/accounts.py`
- `src/pages_admin.py`
- `src/data_manager.py`
- `src/pages_datasets.py`
- `src/audit.py`
- `evidence/s8/pytest_s8.txt`
- `evidence/s8/ui_query.txt`
- `evidence/s8/audit_probe.txt`
- `evidence/s8/admin_375px.png`
- `evidence/s8/created_375px.png`
- `evidence/s9/probe_datasets.txt`
- `evidence/s9/hygiene.txt`
- `evidence/s9/pytest_s9.txt`
- `evidence/s9/dataset_375px_staged.png`
- `evidence/s9/dataset_375px_rejected.png`
- `evidence/s10/trace_metrics.txt`
- `docs/test_matrix.md`
