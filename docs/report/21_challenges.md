# 21. Challenges and Solutions

Draft, Sprint 14. Each item below is a real obstacle met during the build, with the fix and the file
that shows it. Nothing here is a generic "we faced many challenges" paragraph.

## 21.1 Technical challenges

| # | Challenge | What actually happened | Resolution |
|---:|---|---|---|
| C1 | The ingress expected a different port | The operator's tunnel targets `http://web:2026`; the specification said 8501, and the app would have been unreachable | The application moved to 2026 everywhere; recorded as deviation D1 (`docs/architecture.md` §9) |
| C2 | The host's Docker address pools were exhausted | An implicitly-subnetted bridge network could not be created | An explicit `ipam` subnet `10.202.0.0/24`; deviation D7 |
| C3 | A required tunnel token broke `docker compose config` | `${TUNNEL_TOKEN:?}` made every compose command fail when the token was absent, including builds | `env_file` with `required: false`, so the app builds and runs with no Cloudflare credential; deviation D8 |
| C4 | A weak operator password | The supplied admin password is 7 characters, below the 12-character policy | The account is seeded with `must_change_password = 1`: it can sign in once and only set a compliant password; deviation D13. Neither silently accepting nor rewriting the operator's file was acceptable |
| C5 | `docker cp` cannot read a path inside a tmpfs | The backup script staged its snapshot in `/tmp`, which hardening had made a tmpfs, so `docker cp` failed — this was a real defect found by the acceptance gate, not by the author | `backup.sh` streams the snapshot out with `docker exec … cat` and compares checksums; recorded as the S12 gate's blocking finding and its fix |
| C6 | Cloudflare answers 403 to the default Python User-Agent | The public smoke probe reported a healthy deployment as broken | The probe sends a named User-Agent; the fix is in `scripts/smoke_test.sh` and the 403 is reproduced deliberately in `docs/acceptance/S13.md` §6 |
| C7 | The earlier draft's education "others" figure was wrong | 5.7% was code 4 alone, not the aggregate of codes 0/4/5/6 | The figure is restated as 5.69% (n = 123) and 7.05% (n = 468); E2 in `docs/report_evidence.md` §4 |
| C8 | `compileall` cannot write into the bind-mounted tree | The container runs as `app`; the tree belongs to the operator, so the first attempt raised `PermissionError` | The compile step copies the sources into a writable in-container directory; `evidence/s11/test-results/compileall.txt` |
| C9 | A browser harness raced a slow render | The committed UI harness waits on a heading and then acts on controls Streamlit renders later; it timed out at 30 s under load | The gate re-ran the journeys with anchor-based waits and no screenshot gating any check; recorded as finding F-6 in `docs/acceptance/S13.md` and left as a harness-hardening item |
| C10 | Cold start is slow under a read-only root filesystem | The first run rebuilds the Matplotlib font cache; first paint measured at 4 m 15 s on an idle container | Documented as an operational fact in `docs/deployment.md` §10.4 rather than hidden; later sessions paint in ~3 s |

## 21.2 Process challenges

- **Independent verification changes the work.** Every sprint from S0 to S13 was verified by a
  different agent identity from the implementer, and the gates found real defects — S12's blocking
  `backup.sh` failure, S11's file-size row that deselected its own boundary case, S10's chart title
  that typed a number instead of reading it. Those findings are recorded in `docs/acceptance/`, and
  the report cites the verdicts rather than claiming self-certification.
- **Evidence before prose.** The report drafts were written after the artefacts existed, and each
  number in them was taken from a file. Where a claim had no file, it was marked unconfirmed instead
  of written persuasively.
- **Scope discipline.** The binding no-go list (`docs/architecture.md` §8) was the main defence
  against adding a component the brief did not ask for.

## 21.3 Challenges the report cannot resolve

- **The group's own plan is unconfirmed.** A fourteen-day schedule and a four-member division of work
  appear in the earlier draft. No record in this repository confirms either. They are marked
  unconfirmed here and in `docs/rubric_matrix.md` B8, and only the group can settle them.
- **The retention policy is undecided.** Nothing deletes old audit or prediction rows, so the database
  grows with use; the operator decision on how long history must be kept is still open
  (`docs/architecture.md` §10).
- **Fairness work was not attempted.** Named as future work (§23.3), not as a challenge overcome.

## Evidence

- `docs/architecture.md`
- `docs/acceptance/S10.md`
- `docs/acceptance/S11.md`
- `docs/acceptance/S12.md`
- `docs/acceptance/S13.md`
- `evidence/s11/test-results/compileall.txt`
- `evidence/s12/roundtrip.txt`
- `scripts/smoke_test.sh`
- `scripts/backup.sh`
- `docs/deployment.md`
- `docs/report_evidence.md`
- `docs/rubric_matrix.md`
