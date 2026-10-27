# Release notes — AI Hub Campus

`v1.0.0` is tagged and is what `www.aihubcampus.online` serves. It is a single-instance academic
deployment built sprint by sprint from `blueprint.md`; this file records what each sprint changed
in a form an operator can act on, and the first section is the release record itself.

Format: one section per sprint, newest first. Each entry states **what an operator can observe**
(behaviour, file, command), not what the author intended. A claim that needs a command to check
it names the command. Nothing here is dated by guesswork — the git commit is the timestamp.

---

## v1.0.0 — the release candidate (Sprint 16)

```text
VERSION:            v1.0.0
DATE (UTC):         2026-10-27T16:54:11Z      (the tag's commit date)
GIT COMMIT:         tag v1.0.0 — `git rev-parse v1.0.0^{commit}`; the exact sha is printed at the
                    top of evidence/s16/release_gate_attempt.txt, which ran on a clone of this tag
IMAGE ID:           sha256:d8e4cfa00e730734f8160a65afab017a00c78722167622a69d6aed5b0d400cd7
                    (aihubcampus-web:local) — byte-identical to this tree, 30/30 .py files
DATABASE SCHEMA:    0003_dataset_staging
MODEL ARTIFACT:     sha256:48ce02563b2aad9fbf9397603c642b0319be617c57fde8e1fd26ec08d518ad7b
                    (models/best_pipeline.joblib, 8,187 bytes)
MODEL VERSION:      aihubcampus-default-risk-1+48ce02563b2a
DATASET VERSION:    id=1 sha256=a0f0ab49d6326671d6cd83be5c88dcf18007025fe9a53ecd699119c871176ca1
                    rows=30000 columns=25
DEPLOYED AT:        https://www.aihubcampus.online (and https://aihubcampus.online)
```

### What ships

- **One Compose project, one service, no host port.** `aihubcampus` runs `web` (Streamlit, `expose
  2026`) and `cloudflared` (outbound only, started after `web` is healthy). `docker port
  aihubcampus-web-1` prints nothing.
- **The whole application**, S1–S15: the 23-feature prediction form with probability, risk band,
  advice and disclosures; per-account prediction history; administrator user management, dataset
  manager with validation-before-activation, and model evaluation that renders the shipped metrics
  rather than redrawing them; Argon2id credentials, server-side sessions, RBAC and an audit trail.
- **The pinned model artifact** and its manifest, verified at startup by `ml/verify_artifact.py`
  (dataset identity, feature order, class semantics, pickle allowlist, pipeline schema,
  determinism, metrics consistency). The app refuses to serve if verification fails.
- **A hardened runtime**: digest-pinned base image, non-root `app` user, read-only root filesystem,
  `cap_drop: ALL`, `no-new-privileges`, bounded logs, `/tmp` and the cache as bounded `noexec` tmpfs.
- **Four operator scripts**: `verify_release.sh`, `smoke_test.sh`, `backup.sh`, `restore.sh`, each
  with `--help`, each exiting `1` on a failed check and `2` on bad usage.
- **The documents the release is judged on**: `docs/runbook.md` (§10 is the handover),
  `docs/deployment.md`, `docs/model_card.md`, `docs/test_matrix.md`, `docs/RELEASE_NOTES.md`, and
  the evidence in `evidence/s16/`.

### Verified — command → result

| Command | Result |
|---|---|
| `bash evidence/s16/preflight.sh` | running image is byte-identical to the tree: **30/30 .py files, 0 differ**; artifact and manifest hashes match inside and outside the image; no host port |
| `bash evidence/s16/release_gate.sh` (clean clone) | `scripts/verify_release.sh` ran to completion once in this sprint, at `08365e8`: **24 passed, 1 failed** — the single failure was `docs name real files` for `evidence/s16/rollback_drill.txt` and `evidence/s16/live_smoke.txt`, which did not exist yet and are committed in this tag. The confirming run at the tag **did not complete**: the host's Docker daemon stopped creating containers (load average 25–36, 67 containers from other projects), so it stalled at check 12 — `evidence/s16/release_gate_attempt.txt` is the record. **The gate must be re-run by the verifier.** |
| `scripts/smoke_test.sh --url …` | the running stack's hardening checks and the public HTTPS surface — transcript in `evidence/s16/smoke_test.txt` |
| `bash evidence/s16/backup_restore_drill.sh` | bundle written outside the live volume (`27e9a81c…`), second copy taken, restored into a disposable volume: `integrity_check=ok`, **every table count matched**, then the drill volume removed |
| `bash evidence/s16/rollback_drill.sh` | `docker compose down` (no `-v`) → volume survives → `up -d` → healthy on a **new container id**, **same database sha256 `7c815092…`**, public HTTPS `200` |
| `bash evidence/s16/run_release_smoke.sh` | **27 checks, 0 failed**: both roles end to end on the live URL; displayed probability **71.95%** vs the artifact's **71.9535%**; displayed class and model version equal the pipeline's; a 24-column CSV refused as `missing_column`; an empty `LIMIT_BAL` refused before the model ran |

Timestamps, command output and screenshots for each row are in `evidence/s16/` — the transcripts
are the evidence, this table is the index.

**The pytest suite was not re-run in this sprint, deliberately.** No application `.py` file,
dependency, `Dockerfile` or `compose.yaml` has changed since `49540a6`, the commit whose S13 gate
ran the suite — `git diff --stat 49540a6..HEAD -- '*.py' requirements.txt Dockerfile compose.yaml`
lists only `evidence/` helper scripts. Two S16 attempts were killed by host memory pressure from a
concurrent build on this host, not by a test failure, and no completed transcript is claimed.
`evidence/s16/preflight.txt` is what makes the omission safe: the running image's application code
is byte-identical to this tree, so the earlier result applies to what ships. The command, for the
next release or for the gate:

```bash
docker run --rm --network none -v "$PWD:/app:z" -w /app aihubcampus-web:local \
    python -m pytest tests -q -p no:cacheprovider
```

### Known limitations

- **Model recall is 0.3557** at the 0.5 threshold: 855 of the 1,327 held-out defaulters are missed.
  The UI prints that sentence with every result; `docs/model_card.md` §5–§6 is the full record.
- **The probability is uncalibrated** — no calibration test has been run — so it is the model's own
  score, not a risk percentage.
- **A hard refresh signs the user out** (session token lives in Streamlit `session_state`, no
  session cookie) — F-1 in `docs/deployment.md` §10.5.
- **The `_streamlit_xsrf` cookie is not marked `Secure`**, and `http://` answers `200` instead of
  redirecting — F-2 and F-3, both consequences of TLS terminating at the Cloudflare edge, both
  needing an operator zone action rather than a code change.
- **No fairness audit, no drift monitoring, no external validation.** `SEX`, `EDUCATION`,
  `MARRIAGE` and `AGE` are inputs and group error rates were never measured.
- **The live database carries demo residue**: 21 predictions, 8 dataset rejections, 7 staged dataset
  versions and five deactivated synthetic administrator accounts (`s13_tunnel_check`, `s13_probe`,
  `s15_demo_check`, `s15_diag`, `s16_release_check`) left by the S13/S15/S16 rehearsals. None of it
  is user data; the activated dataset is still version 1, the seed CSV, and the only two active
  accounts are the operator's `ds_hafyz` and the demo `demo_user`.
- **The tunnel token, `APP_SESSION_SECRET` and both initial passwords are operator-held** and are
  not in the repository. `docs/runbook.md` §10.3 lists the names; nothing here can verify a value
  it must not read.

### Rollback plan

```text
application:  git checkout <previous tag or commit> && docker compose build web && docker compose up -d web
              the volume is untouched; migrations only ever add
database:     scripts/backup.sh                                   # before anything
              docker compose stop web
              scripts/restore.sh --backup <bundle> --to-volume aihubcampus_app_storage --allow-live --yes
              docker compose start web && scripts/smoke_test.sh
```

The rollback path was exercised end to end for this release: `evidence/s16/rollback_drill.txt`
takes the stack down with `docker compose down` (never `-v`), proves the volume survived, brings it
back on the same volume, and shows the database byte-identical afterwards.

A release is marked COMPLETE only with the evidence attached, never on the strength of this file
alone (blueprint §9 SPRINT 16). The independent acceptance record for this sprint is
`docs/acceptance/S16.md`, written by the verification agent — not by the implementer.

---

## Sprint 13 — live on www.aihubcampus.online through the Cloudflare tunnel

**Commit:** `b3d014447133` — the tree `scripts/verify_release.sh` ran against, recorded in `evidence/s13/release_gate.txt` (25 checks, 0 failed) · **Branch:** `s13/cloudflare-tunnel`

### Live

- **The application is public over HTTPS.** `https://www.aihubcampus.online` and
  `https://aihubcampus.online` both serve the app through the operator's existing tunnel
  (`aeab965f-…`), which forwards to `http://web:2026` on the project network. Nothing is published
  on a host port: `docker port aihubcampus-web-1` is empty.
- **`cloudflared` is a Compose service**, started only after `web` reports healthy, so the tunnel
  cannot forward into a container that is still booting. Its token is read from
  `.env.cloudflared` (`env_file`, `required: false`), never from the image or a command line.
- **Both roles complete their journeys through the tunnel.** Administrator: sign-in, prediction,
  history, user management, dataset upload (staged, not activated), model evaluation. User:
  prediction and history only — the three administrator sections are not offered at all.
- **`scripts/smoke_test.sh --url …` now works against the public URL.** Cloudflare answers `403`
  to the default `Python-urllib/3.x` User-Agent, which made a healthy deployment look broken; the
  probe sends `aihubcampus-smoke-test/1.0` instead. 16 checks, 0 failed.

### Known, documented

- A **hard refresh signs the user out** — the session token lives only in Streamlit
  `session_state` and there is no session cookie. Recorded as F-1 in `docs/deployment.md` §10.5.
- The `_streamlit_xsrf` cookie is not marked `Secure`, and `http://` answers `200` instead of
  redirecting. Both follow from TLS terminating at the Cloudflare edge; both are recorded as F-2
  and F-3 with the operator-side remedy.

---

## Sprint 12 — production-like Docker hardening and recovery

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

### Fixed after the independent gate (F-1)

- **`scripts/backup.sh` could not produce a backup on the hardened stack.** It staged the
  `VACUUM INTO` snapshot in the container's `/tmp` and pulled it out with `docker cp`, but S12
  makes `/tmp` a tmpfs and Docker cannot copy a path inside a container tmpfs — so the script
  exited `1` on the very stack this sprint ships. The snapshot is now **streamed out with
  `docker exec … cat`**, then checked three ways before it is allowed into the bundle: the exec
  exited zero, the file is non-empty, and the host sha256 equals the one the container computed.
  `docs/runbook.md` §4 and `README.md` describe the stream, not the copy. Re-captured on the
  hardened runtime in `evidence/s12/backup.txt` and `evidence/s12/roundtrip.txt`.

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

## Release record template

The block at the top of this file is the record `v1.0.0` filled in: version, date, commit, image
id, schema version, model artifact, dataset version, what changed, what was verified with which
command, the known limitations, and the rollback plan. Keep the same shape for the next release —
the fields are the ones an operator needs to answer "what is running, and can I put it back?".
