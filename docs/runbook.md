# Operations runbook — AI Hub Campus

Sprint 12 deliverable (blueprint §7 operator checklist, §9 SPRINT 12). This is the document
an operator opens at 02:00 when something is wrong. It assumes the stack is the one described
in `docs/architecture.md` §2: one Compose project named `aihubcampus`, one `web` service, one
`cloudflared` tunnel client, one named volume, no published host port.

Every command below is a real file or a real Compose subcommand — `scripts/verify_release.sh`
fails if a `scripts/…` or `evidence/…` path named in this document does not exist.

```
project   aihubcampus
service   web                (the Cloudflare ingress targets this name: http://web:2026)
volume    aihubcampus_app_storage   → /app/storage (the only writable mount)
image     aihubcampus-web:local
port      expose 2026 only — never a `ports:` mapping
```

## 0. The one rule

> **Never run `docker compose down -v`.** The `-v` deletes `aihubcampus_app_storage`, and that
> volume holds the only copy of the database — users, prediction history, dataset versions,
> audit trail. There is no other copy unless `scripts/backup.sh` has run. `docker compose down`
> without `-v` is safe; `-v` is not. See §6 for teardown that keeps the data.

A second rule: **a secret never appears in a terminal, a log, a commit or a screenshot.**
Credentials live in `.env` (mode 600, git-ignored) and are read by Compose, never echoed. The
tunnel token lives in `.env.cloudflared`. If a token or password is ever displayed, rotate it —
see `docs/deployment.md` §7.

## 1. Is it up?

```bash
docker compose ps                       # web should be "Up (healthy)"
docker compose ps -q web                # the container id, for the commands below
docker compose logs --tail 50 web       # bounded to 10 MB × 5 files by compose.yaml
```

`docker compose ps` reports four different things; they are not the same problem:

| Status | Meaning | Next step |
|---|---|---|
| `Up (healthy)` | health probe answers `ok` | nothing |
| `Up (health: starting)` | still inside `start_period: 40s` | wait 40 s, re-check |
| `Up (unhealthy)` | app process alive, probe failing | §2 |
| `Restarting` / `Exited (1)` | the process dies at startup | §3 |
| nothing listed | the container does not exist | `docker compose up -d web` |

The probe is a Python one-liner inside the container (`urllib` against
`http://127.0.0.1:2026/_stcore/health`) — the image has no `curl` on purpose. To run it by hand:

```bash
docker compose exec web python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:2026/_stcore/health', timeout=3).read().decode())"
# expected: ok
```

The ten-second version of all of the above — plus the hardening checks and the artifact gate —
is the smoke test:

```bash
scripts/smoke_test.sh
# RESULT: 15 passed, 0 failed, 1 skipped
# SMOKE TEST PASSED — the running stack is the hardened stack and it serves.
```

## 2. It is up but unhealthy

Read the log before touching anything:

```bash
docker compose logs --tail 200 web
```

The four failures seen in practice, and what each means:

| Log line | Cause | Fix |
|---|---|---|
| `model artifact failed verification` | `models/` inside the image does not match `model_manifest.json` | the image is wrong, not the data — rebuild from a clean checkout (§4 of `docs/deployment.md`) |
| `database is locked` | a second writer (a restore, a manual `sqlite3` session) holds the write lock | close the other writer; the app retries within its 5 s busy timeout |
| `no such table` / migration error | the volume was mounted over an older, incompatible database | restore a backup (§5), do not hand-edit the schema |
| `Address already in use` | another process inside the container holds 2026 | restart the container; if it persists, the image is not the one in this repo |

If the log is clean and the probe still fails, restart the container — the schema migration
and the artifact check both re-run at startup, and both are idempotent:

```bash
docker compose restart web
docker compose ps                        # wait for (healthy)
```

A restart is safe by design: the database lives on the volume, not in the container, and
`src/db.py` applies only the migrations that are missing. Sprint 11 proved this at deployment
level (`docs/test_matrix.md` row T11, `evidence/s11/restart.txt`).

## 3. It will not start

```bash
docker compose ps -a                     # exit code
docker compose logs --tail 200 web
docker inspect --format '{{.State.ExitCode}} {{.State.Error}}' "$(docker compose ps -aq web)"
```

| Exit code | Usual cause |
|---|---|
| 1 | a Python traceback in the log above it — fix the cause, do not loop restarts |
| 125 | Compose rejected the configuration: `docker compose config --quiet` prints why |
| 137 | killed (OOM or `docker kill`) — check `dmesg` on the host for the OOM line |
| 143 | SIGTERM — a stop/restart, not a crash |

A configuration rejection is the common one after an edit. Validate without starting anything:

```bash
docker compose config --quiet            # silent = valid
```

A missing `.env` is *not* a startup failure for `docker compose config`, but it is for the app:
`src/config.py` refuses to invent a secret. The file must exist next to `compose.yaml` with
mode 600 (see `docs/deployment.md` §3).

## 4. Backup

```bash
scripts/backup.sh                        # → backups/aihubcampus-<UTC stamp>.tar.gz
scripts/backup.sh --out /srv/backups --keep 14
```

What it does, in order: refuses if the container is not running and healthy → takes a
**`VACUUM INTO` snapshot inside the container** (not a file copy: the database runs in WAL
mode, so copying the `.db` alone can miss committed pages still in the `-wal`) → streams the
snapshot out with `docker exec … cat` and compares the SHA-256 the container computed on the
snapshot with the host file's → captures
`model_manifest.json`, `metrics.json` and the `dataset_versions` rows → writes
`manifest.json`/`MANIFEST.txt` with a checksum per file, the row counts, the git commit and the
image id → packs a tarball and a `.sha256` beside it → **unpacks its own tarball and verifies
every checksum, `integrity_check` and row count**.

The last step is the point: a backup that cannot be read is not a backup. If `scripts/backup.sh`
exits non-zero, there is no usable backup and the run must be treated as failed.

`backups/` is git-ignored. Copy the tarball off this host — a backup on the same disk as the
database is not a backup. Retention: `--keep N` prunes all but the newest N tarballs in the
output directory.

The live stack is not stopped or paused for a backup. The snapshot is one read transaction.

## 5. Restore, and rollback

Restore is the only operation that can destroy the only copy of the data, so
`scripts/restore.sh` verifies before it writes and refuses to touch the live volume by default.

**5a. Rehearse into a directory** (safe, no Docker volume, this is the S12 acceptance path):

```bash
scripts/restore.sh --backup backups/aihubcampus-<stamp>.tar.gz --to-dir /tmp/restore-check
```

**5b. Rehearse into a disposable volume** (proves the whole path, still nothing live):

```bash
docker volume create aihubcampus-restore-check
scripts/restore.sh --backup backups/aihubcampus-<stamp>.tar.gz --to-volume aihubcampus-restore-check
```

Both verify the tarball's `.sha256`, every file against `manifest.json`, `PRAGMA
integrity_check`, the row count of every table, the SHA-256 of the restored file, and finally
open the restored copy and re-count. A failure aborts before anything is written.

**5c. Roll back the live database** — only after a fresh backup and with the service stopped:

```bash
scripts/backup.sh                                    # 1. capture the current state first
docker compose stop web                              # 2. nothing may hold the file open
scripts/restore.sh --backup backups/aihubcampus-<stamp>.tar.gz \
                   --to-volume aihubcampus_app_storage --allow-live --yes   # 3. verified restore
docker compose start web                             # 4. migrations re-run, artifact re-verifies
scripts/smoke_test.sh                                # 5. prove it
```

`--allow-live` additionally requires `--yes` and refuses while the service is running. If step 3
fails, nothing was written and the old database is still in place — that is why the checks run
first.

**5d. Roll back the application.** The image is not the data. To go back to a previous build,
check out that commit and rebuild; the volume is untouched and the migrations are additive:

```bash
git log --oneline -20                    # find the commit you want
git checkout <commit> && docker compose build web && docker compose up -d web
scripts/smoke_test.sh
```

If the older code predates a migration the current database already applied, the app still
starts (migrations only ever add). If it refuses, restore the database backup taken at the same
time as that release — which is why the backup manifest records the git commit.

## 6. Safe teardown

| Command | Containers | Network | **Volume (the data)** | Use for |
|---|---|---|---|---|
| `docker compose stop web` | stopped, kept | kept | **kept** | pausing, a restore |
| `docker compose down` | removed | removed | **kept** | rebuilding from scratch |
| `docker compose down -v` | removed | removed | **DELETED** | never — this is the disaster |
| `docker compose down --rmi local` | removed | removed | **kept** | reclaiming image space |

Stopping the stack for maintenance:

```bash
scripts/backup.sh && docker compose stop web
```

Bringing it back:

```bash
docker compose up -d web && scripts/smoke_test.sh
```

If someone has already run `down -v`: the volume is gone. Stop, do not start the stack (a
start would create an empty database and make the loss look like normal operation), and restore
the newest backup into a fresh volume with §5c. Then find out why the backup was not on another
host.

## 7. The scripts, in one table

| Script | Answers | Touches live data |
|---|---|---|
| `scripts/smoke_test.sh` | is the running stack hardened and serving? | no (read-only probes) |
| `scripts/verify_release.sh` | may this tree be deployed? | no (static + smoke) |
| `scripts/backup.sh` | can this state be recovered? | no (one read transaction) |
| `scripts/restore.sh` | is the backup real, and how do I put it back? | only with `--allow-live --yes` |

All four print `--help`, exit `2` on bad usage and `1` on a failed check, and never print a
secret.

## 8. Routine

| When | Do | Why |
|---|---|---|
| after every deploy | `scripts/smoke_test.sh` | the deploy is not done until the probe passes |
| daily | `scripts/backup.sh --out /srv/backups --keep 14` | 14 days of recoverable history |
| weekly | `scripts/restore.sh --backup <newest> --to-dir /tmp/restore-check` | an unexercised backup is a guess |
| monthly | `scripts/verify_release.sh --build --with-tests` | the tree still builds and the suite still passes |
| on any alert | §1 → §2 → §3, in that order | never restart first; the log is the evidence |

## 9. Where the rest of the answer is

| Question | Document |
|---|---|
| what the system is, and why port 2026 | `docs/architecture.md` |
| the exact operator sequence to deploy | `docs/deployment.md` |
| what was tested, and the command that proves it | `docs/test_matrix.md` |
| what changed in this release | `docs/RELEASE_NOTES.md` |
| what the model is, and what it may not be used for | `docs/model_card.md` |
| the S12 evidence transcripts | `evidence/s12/` |
| the S16 release evidence (gates, backup, rollback, live smoke) | `evidence/s16/` |
| the sprint acceptance records | `docs/acceptance/` |

## 10. Handover — what the operator needs, in one place

Sprint 16 deliverable (blueprint §9 SPRINT 16): the operational commands, the secret input list,
the health and backup routine, the reproducibility commands and the deployment URL. Everything
below is a copy of a command that is exercised elsewhere in this file or in `evidence/s16/`; it
is gathered here so the handover is one section, not six.

### 10.1 The deployment

| | |
|---|---|
| Public URL | **https://www.aihubcampus.online** (and `https://aihubcampus.online`) |
| Ingress | the operator's existing Cloudflare tunnel, `→ http://web:2026` on the project network |
| Host | `ridergami2`, user `ec-user`, repository `/home/ec-user/non_prod/hafyz_ds` |
| Compose project | `aihubcampus` — one `web` service, one `cloudflared` client, one volume |
| Release | tag `v1.0.0` (`git describe --tags --exact-match`) |
| Host ports | **none published** — `docker port aihubcampus-web-1` is empty by design |
| TLS | terminated at the Cloudflare edge; the origin is plain HTTP inside the Docker network |

### 10.2 Operational commands

```bash
cd /home/ec-user/non_prod/hafyz_ds

docker compose ps                      # is it up, and healthy?
docker compose logs --tail 100 web     # bounded 10 MB × 5; the log is the evidence
docker compose restart web             # after a config change; the volume is untouched
docker compose up -d                   # start (or reconcile) web + cloudflared
docker compose stop web                # pause; data kept — this is the restore precondition
docker compose down                    # remove containers + network; data KEPT
# docker compose down -v               # NEVER — this deletes aihubcampus_app_storage

scripts/smoke_test.sh --url https://www.aihubcampus.online   # 16 checks, the 10-second answer
scripts/verify_release.sh --with-tests                        # may this tree be deployed?
scripts/backup.sh --out /srv/backups --keep 14                # a backup you can restore
scripts/restore.sh --backup <bundle> --to-dir /tmp/restore-check   # prove the backup
```

The four scripts print `--help`, exit `2` on bad usage and `1` on a failed check, and never print
a secret. §7 lists what each one touches.

### 10.3 Secret input list — names only, never values

Two files, mode 600, git-ignored, read by Compose and never by a command line. `.env.example` and
`.env.cloudflared.example` carry placeholders; the operator supplies the values.

| File | Variables (names only) |
|---|---|
| `.env` | `APP_ENV`, `APP_DOMAIN`, `APP_SESSION_SECRET`, `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_PASSWORD`, `INITIAL_USER_USERNAME`, `INITIAL_USER_PASSWORD`, `DATA_RETENTION_DAYS` |
| `.env.cloudflared` | `TUNNEL_TOKEN` |

`APP_SESSION_SECRET` and both passwords are generated by the operator (24+ characters,
`python -c "import secrets; print(secrets.token_urlsafe(48))"`); the tunnel token comes from the
Cloudflare dashboard. How to rotate each one: `docs/deployment.md` §7. If a value is ever
displayed, rotate it.

### 10.4 Health — what to check, and how often

| When | Command | Pass looks like |
|---|---|---|
| after every deploy | `scripts/smoke_test.sh --url …` | `SMOKE TEST PASSED`, 0 failed |
| daily | `curl -sS -A 'aihubcampus-ops/1.0' https://www.aihubcampus.online/_stcore/health` | body `ok`, status 200 |
| daily | `docker compose ps` | `web` → `Up (healthy)`, `cloudflared` → `Up` |
| weekly | `scripts/restore.sh --backup <newest> --to-dir /tmp/restore-check` | `Restored and verified` |
| monthly | `scripts/verify_release.sh --with-tests` | `VERDICT: PASS` |
| on any alert | §1 → §2 → §3, in that order | never restart first |

A `curl` to the public host must send an explicit `User-Agent`: Cloudflare answers `403` to the
default `Python-urllib/3.x` agent, which makes a healthy deployment look broken.

### 10.5 Backup and restore, in the order they are run

```bash
scripts/backup.sh --out /srv/backups --keep 14      # 1. snapshot (live, no downtime)
ls -l /srv/backups/aihubcampus-*.tar.gz*            # 2. a .tar.gz and its .sha256, side by side
cp /srv/backups/aihubcampus-<stamp>.tar.gz* /media/offsite/   # 3. off this host — a backup on
                                                    #    the same disk is not a backup
scripts/restore.sh --backup /srv/backups/aihubcampus-<stamp>.tar.gz \
                   --to-dir /tmp/restore-check      # 4. rehearse it, weekly
```

A restore into the live volume is §5c and needs `--allow-live --yes` with the service stopped.
The bundle holds the database snapshot, the model manifest, the metrics and the active dataset
metadata; it holds no credential. The release backup for `v1.0.0` is recorded in
`evidence/s16/backup_restore_drill.txt` (bundle path and SHA-256), and it was restored once into a
disposable volume before this release was marked complete.

### 10.6 Reproducibility — rebuild this release from the tag

```bash
git clone /home/ec-user/non_prod/hafyz_ds /tmp/aihubcampus-release
cd /tmp/aihubcampus-release && git checkout v1.0.0
cp /path/to/operator/.env .env && chmod 600 .env                       # the two operator inputs
cp /path/to/operator/data/UCI_Credit_Card.csv data/UCI_Credit_Card.csv
scripts/verify_release.sh --build --with-tests                          # gate + build + suite
docker compose up -d && scripts/smoke_test.sh --url https://www.aihubcampus.online
```

The image builds from a digest-pinned base (`Dockerfile`), the model artifact is committed, and
the seed dataset's SHA-256 is asserted by `ml/verify_artifact.py`, so the same tag plus the same
two inputs produces the same behaviour. What is *not* reproducible from the tag: the live database
(that is what the backup is for) and the tunnel token (the operator's).

### 10.7 Where the evidence is

| Question | Answer |
|---|---|
| did the release gates pass, and with what output | `docs/acceptance/S16.md`, `evidence/s16/` |
| what is deployed right now, and is it this tree | `evidence/s16/preflight.txt` |
| can the data be recovered | `evidence/s16/backup_restore_drill.txt` |
| does the stack come back after a teardown | `evidence/s16/rollback_drill.txt` |
| do both roles work on the live URL | `evidence/s16/live_smoke.txt` + the `s16_*.png` screenshots |

