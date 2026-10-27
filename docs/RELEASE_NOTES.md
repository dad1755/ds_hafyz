# Release notes — AI Hub Campus

The project does not tag a release yet: it is a single-instance academic deployment on
`www.aihubcampus.online`, built sprint by sprint from `blueprint.md`. This file records what
each sprint changed in a form an operator can act on, and carries the template the release
candidate (S16) will fill in.

Format: one section per sprint, newest first. Each entry states **what an operator can observe**
(behaviour, file, command), not what the author intended. A claim that needs a command to check
it names the command. Nothing here is dated by guesswork — the git commit is the timestamp.

---

## Unreleased — Sprint 12: production-like Docker hardening and recovery

**Commit:** the sha is printed by `evidence/s12/release_gate.txt` (the gate records the tree it ran against) · **Branch:** `s12/docker-hardening-recovery`

### Changed

- **Base image pinned by digest.** `Dockerfile` builds `FROM python:3.12-slim@sha256:2f17fc04…`
  instead of the moving `python:3.12-slim` tag, so a rebuild in six months produces the same
  image. Moving the pin is now a deliberate edit, not a side effect of `docker pull`.
- **The container filesystem is immutable.** `compose.yaml` sets `read_only: true` on `web`,
  with `/tmp` and `/home/app/.cache` as bounded `noexec`/`nosuid` tmpfs. The only writable
  path is the `app_storage` volume at `/app/storage`.
- **All Linux capabilities dropped** (`cap_drop: ALL`) in addition to the existing
  `no-new-privileges`. The app needs none: it binds 2026, reads files, writes its volume.
- **Container logs bounded** to 10 MB × 5 files, so a chatty day cannot fill the host disk.

### Added

- `scripts/backup.sh` — consistent SQLite snapshot via `VACUUM INTO` inside the container, plus
  the model manifest, metrics and dataset metadata; checksums every file, then unpacks its own
  tarball and verifies it.
- `scripts/restore.sh` — verifies the tarball, every checksum, `integrity_check` and every row
  count **before** writing; restores to a directory or a volume; refuses the live volume without
  `--allow-live --yes` and a stopped service.
- `scripts/smoke_test.sh` — fifteen checks against the running container (health, non-root,
  read-only rootfs, no published ports, dropped caps, single writable mount, database integrity,
  artifact verification, secret scan), with an optional `--url` for the public HTTPS surface.
- `scripts/verify_release.sh` — the mechanical pre-deploy gate: repo state, compose contract,
  image contract, secret scan, presence of every script and evidence path the docs name, the
  smoke test, and optionally the full pytest suite.
- `docs/runbook.md` — health, logs, backup, restore, rollback and safe teardown. The rule it
  opens with: **never `docker compose down -v`**.
- `docs/deployment.md` — the exact operator sequence, the secret input list (names only), and a
  20-line security checklist.
- `docs/RELEASE_NOTES.md` — this file.

### Unchanged, deliberately

- **Port 2026, not 8501.** The Cloudflare ingress targets `http://web:2026`
  (`docs/architecture.md` §5). The blueprint's 8501 is a default this deployment does not use.
- **No `ports:` mapping.** Still `expose: 2026` only. No host port has ever been published.
- **No change to the tunnel, DNS or the `cloudflared` service** — that is Sprint 13.

### Verified

See `evidence/s12/` for the verbatim transcripts: the fresh-checkout build and run, the restart
that preserved the database, the backup → restore round-trip on a copy of the volume, the secret
scan, and the release gate output — 26 mechanical checks plus the full 285-test suite re-run
inside the digest-pinned image. Certification of this sprint is the independent verification
agent's, per blueprint §0.

---

## Sprint 11 — automated testing and adversarial verification

285 tests across `tests/`, the T01–T12 matrix in `docs/test_matrix.md`, adversarial cases for
RBAC sweeps, upload limits, path containment, secret patterns and origin handling. Restart
persistence proven twice (unit and deployment level).

## Sprint 10 — admin model evaluation and insight panels

Admin evaluation page renders the shipped figures and metrics rather than redrawing them, so
the page cannot disagree with `models/metrics.json`.

## Sprint 9 — admin dataset manager

Staged uploads under a generated name on the volume, one active dataset pointer, validation
before activation, and the distinction between the uploaded dataset and the deployed model.

## Sprint 8 — administrator user management

List, create, edit, reset password, deactivate. Every action audited.

## Sprint 7 — user prediction UI

The 23-feature form, the result panel with probability, band and recommendations, and the
account's own prediction history.

## Sprint 6 — SQLite, authentication, session and role guards

Argon2id hashing, session tokens, RBAC, login throttling, idempotent migrations.

## Sprints 1–5 — container skeleton, schema, EDA, training, inference

See `docs/architecture.md` §11 and `docs/test_matrix.md` for the evidence of each.

---

## Release candidate template (S16)

```text
VERSION:            vX.Y.Z
DATE (UTC):         YYYY-MM-DDTHH:MM:SSZ
GIT COMMIT:         <sha>  (branch <name>)
IMAGE ID:           sha256:<digest>  (aihubcampus-web:<tag>)
DATABASE SCHEMA:    <highest applied schema_migrations version>
MODEL ARTIFACT:     sha256:<digest>  (models/best_pipeline.joblib)
DATASET VERSION:    id=<n> sha256=<digest> rows=<n>

CHANGED:
  -

VERIFIED (command → result):
  - scripts/verify_release.sh --build --with-tests →
  - scripts/smoke_test.sh →
  - scripts/backup.sh →  (bundle path, sha256)
  - scripts/restore.sh → (target, checksum compare)

KNOWN LIMITATIONS:
  -

ROLLBACK PLAN:
  application: <previous commit>
  database:    <backup bundle>
```

A release is marked COMPLETE only with the evidence attached, never on the strength of this
file alone (blueprint §9 SPRINT 16).
