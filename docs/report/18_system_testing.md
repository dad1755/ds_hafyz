# 18. System Testing

Draft, Sprint 14. The deliverable table is `docs/test_matrix.md`; the raw transcript is
`evidence/s11/test-results/pytest_all_verbose.txt`; the machine check that every cited test id
appears in that transcript as PASSED is `evidence/s11/test-results/t_matrix_extract.txt`.

## 18.1 Scale and shape of the suite

**285 test cases, 0 failed, 0 error, 0 skipped**, in 598.66 s, run inside the project image
(Python 3.12.14, pytest 9.1.1). The suite was re-run on the digest-pinned base in Sprint 12: 285
passed in 572.74 s (`evidence/s12/release_gate.txt`). The suite grew from 263 cases at S10 to 285 at
S11, the 22 new cases being the three cross-cutting journeys and the adversarial set.

The twelve required system tests map to real node ids rather than to prose:

| ID | Requirement | Observed |
|---|---|---|
| T01 | An admin and a user both sign in and are served different views | Admin navigation is exactly six sections, the user's exactly three; both sessions are database rows |
| T02 | Wrong credentials refused generically, repeated failures throttled, lock expires | 5th failure locks the username for 15 minutes even for the correct password; a different username is unaffected; after lockout + 1 s the correct password works |
| T03 | A user is barred from the admin screen and from the functions behind it | 14-function sweep: `PermissionDenied` and one `auth.denied` row each; forged/absent token raises `SessionInvalid` |
| T04 | An admin adds and edits a user, and the change persists | Created account signs in; display-name edit and role change read back from SQLite in a fresh connection |
| T05 | A valid 25-column CSV is accepted and staged with counts | 30,000 records, 25 columns, 23,364 / 6,636, `status=validated`, `is_active False`, preview aggregates only |
| T06 | A malformed CSV is rejected with a clear reason | Dropping `PAY_6` → `missing_column` and the persisted reason; no version row; one rejection row; quarantine copy removed |
| T07 | A valid 23-field submission returns class, probability and advice | Class 1, probability 0.7195348837209302, band High, advice text, model version, three disclosures |
| T08 | Invalid input is rejected before the model | Exactly one error naming `LIMIT_BAL`, no result panel, 0 rows written |
| T09 | The app's class and probability match the standalone pipeline | Bit-identical `repr()` over six synthetic rows; class equals `int(probability >= 0.5)` |
| T10 | Tier mapping and advice match the score boundaries | 9 edge cases plus a 10,001-point sweep: one band everywhere, no skips, no reversals |
| T11 | A restart keeps data, model and protected access | Proven at unit level and by a real `--force-recreate`; row counts kept, artifact re-verified |
| T12 | The full journey login → prediction → history → logout works | One session completes it; the session is revoked and the prediction row survives |

## 18.2 Adversarial and cross-cutting checks

Beyond the happy path, the suite and the probes assert: the RBAC sweep described above; the upload
size limit at exactly 10 MiB accepted and 10 MiB + 1 byte refused, including through the quarantine
path; quarantine containment against a traversal name (`../../etc/passwd`), a generated stored name,
mode 0600; the secret-pattern scan over every tracked file; that the SQLite file, the dataset and the
artifact are **not** downloadable — six candidate paths all return the SPA shell and none contains
the `SQLite format 3\0` header or the artifact's first bytes; that no password, hash or key block
appears in the container log; and that XSRF protection and CORS remain on, with a foreign-origin
WebSocket upgrade answered `403` and a real-origin upgrade `101`.

## 18.3 What testing does not cover

- **No load or soak testing.** One instance, one process; no concurrency measurement, no latency
  budget. Cold start was measured (4 m 15 s to first paint on an idle container, ~3 s for later
  sessions) and is recorded as an operational fact, not as a performance test.
- **No cross-browser matrix.** Chromium only (Playwright's bundled build).
- **No screen-reader or WCAG audit.** Layout was checked at 375 px and 1280 px for overflow only.
- **No penetration test.** The security checks are targeted assertions, not an adversarial audit.
- **No user-acceptance testing with real users.** Usability is asserted from layout checks, not
  measured.

## 18.4 How to reproduce

```bash
docker run --rm -v "$PWD:/app:z" -w /app aihubcampus-web:local \
    python -m pytest tests -v -p no:cacheprovider
python3 evidence/s11/extract_matrix.py
scripts/verify_release.sh --build --with-tests
```

## Evidence

- `docs/test_matrix.md`
- `evidence/s11/test-results/pytest_all_verbose.txt`
- `evidence/s11/test-results/t_matrix_extract.txt`
- `evidence/s11/test-results/compileall.txt`
- `evidence/s11/test-results/check_no_secrets.txt`
- `evidence/s11/probe_http.txt`
- `evidence/s11/probe_logs.txt`
- `evidence/s11/restart.txt`
- `evidence/s12/release_gate.txt`
- `docs/acceptance/S11.md`
