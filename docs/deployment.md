# Deployment — AI Hub Campus

Sprint 12 deliverable (blueprint §7 deployment contract, §9 SPRINT 12). The exact operator
sequence, in order, with no step left to memory. `docs/runbook.md` covers what to do when one
of them fails.

**Scope of this document:** deploying the `aihubcampus` Compose project on ridergami2 and
attaching it to the already-existing Cloudflare tunnel for `www.aihubcampus.online`. Creating
or editing the tunnel, its ingress rules or its DNS records is **not** part of this sequence
(§8).

## 1. Preconditions

| Requirement | Check | Expected |
|---|---|---|
| Docker + Compose v2 | `docker compose version` | `v2.x` or newer |
| The repo at the release commit | `git log --oneline -1` | the commit named in `docs/RELEASE_NOTES.md` |
| Clean tree | `git status --short` | no modified tracked files |
| The dataset present | `ls -l data/UCI_Credit_Card.csv` | 30 000 rows + header, ~30 MB |
| Free disk for the image | `docker system df` | ≥ 2 GB |
| Nothing already bound to the project name | `docker compose ps` | `web` absent, or this stack |

The dataset is **not** in the image (`.dockerignore`) and is **not** in git. It is mounted
read-only from `data/UCI_Credit_Card.csv` by `compose.yaml`; the app hashes and counts it once at
startup to record dataset version 1. A deploy without the file fails at startup with a named
error — it does not silently run on a different dataset.

## 2. What is in the image, and what is not

Baked in: application code (`app.py`, `src/`, `ml/schema.py`), the shipped model
(`models/best_pipeline.joblib` + `model_manifest.json` + `metrics.json`), the EDA figures the
admin page renders, the operator scripts, and the Streamlit config. The base image is pinned by
digest, not by tag.

Deliberately absent: `.env`, `.env.cloudflared`, the dataset, the database, any credential.
`scripts/verify_release.sh` asserts that `/app/.env` does not exist in the image and that no
credential-shaped variable is in its `Config.Env`.

At runtime the container has an **immutable root filesystem** (`read_only: true`), `/tmp` and
`/home/app/.cache` as bounded tmpfs, **all capabilities dropped**, `no-new-privileges`, and
exactly one writable mount: the `aihubcampus_app_storage` volume at `/app/storage`.

## 3. Secrets — names, never values

Two files, both git-ignored, both mode 600, both read by Compose (never copied into the image,
never echoed by a script in this repo):

`.env` — read by the `web` service:

| Variable | What it is | How it is produced |
|---|---|---|
| `APP_ENV` | `production` on this host | set by the operator |
| `APP_SESSION_SECRET` | signs session tokens | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `INITIAL_ADMIN_USERNAME` / `INITIAL_ADMIN_PASSWORD` | the first administrator, consumed by `scripts/init_admin.py` | chosen by the operator; a generated 24+ char password |
| `INITIAL_USER_USERNAME` / `INITIAL_USER_PASSWORD` | the demo user, same mechanism | as above |

`.env.cloudflared` — read by the `cloudflared` service only:

| Variable | What it is | Where it comes from |
|---|---|---|
| `TUNNEL_TOKEN` | the remotely-managed tunnel token | the Cloudflare dashboard, inserted by the operator |

Create them from the committed placeholders, never from memory:

```bash
cp .env.example .env && chmod 600 .env
cp .env.cloudflared.example .env.cloudflared && chmod 600 .env.cloudflared
# edit both, filling in values; do not paste them into a shell, a chat or an issue
```

Rules that do not bend:

- A value never appears in a command line (`ps` shows it), a log, a commit, a screenshot or a
  ticket. `scripts/check_no_secrets.py` scans the tree; run it before every commit.
- `.env` is read by Compose, not by the app. The app reads only non-secret settings through
  `src/config.py`.
- Rotating a credential means editing the file and recreating the service (§7). It never means
  editing code.

## 4. First deploy

```bash
# 1. the gate — do not skip: it is the difference between "deployed" and "deployed correctly"
scripts/verify_release.sh --build --with-tests

# 2. build (the gate already did this; re-run only if you changed something)
docker compose build web

# 3. start
docker compose up -d web

# 4. wait for the health probe, do not assume
docker compose ps                       # web  Up (healthy)

# 5. seed the operator accounts, once, from .env — prints usernames and hash prefixes only
docker compose exec web python scripts/init_admin.py

# 6. prove the deployment
scripts/smoke_test.sh
```

Step 5 is idempotent in the sense that matters: it refuses to overwrite an existing account
rather than resetting its password. Re-running it after the first success changes nothing.

Expected tail of step 3, in `docker compose logs web`:

```
Uvicorn server started on 0.0.0.0:2026
You can now view your Streamlit app in your browser.
```

## 5. Redeploy after a change

```bash
scripts/verify_release.sh --build --with-tests   # gate
docker compose build web                          # rebuild
docker compose up -d web                          # recreate — the volume is untouched
scripts/smoke_test.sh                             # prove
scripts/backup.sh --out /srv/backups --keep 14    # capture the state you just deployed
```

`docker compose up -d` recreates the container; it never removes the volume. The database, the
migrations and the artifact verification all survive a recreate — that is the T11 row in
`docs/test_matrix.md`.

## 6. Security checklist (pre-release, tick every line)

Run `scripts/verify_release.sh` — it asserts most of this mechanically. The list is here so a
human can confirm the *intent*, not just the exit code.

| # | Control | Where it lives | Checked by |
|---|---|---|---|
| 1 | Container runs as a non-root user (uid 1001) | `Dockerfile` `USER app` | `smoke_test.sh`, `verify_release.sh` |
| 2 | Root filesystem is read-only | `compose.yaml` `read_only: true` | `smoke_test.sh` |
| 3 | Exactly one writable mount, at `/app/storage` | `compose.yaml` `volumes:` | `smoke_test.sh` |
| 4 | `/tmp` is a bounded, `noexec`, `nosuid` tmpfs | `compose.yaml` `tmpfs:` | `smoke_test.sh` |
| 5 | All Linux capabilities dropped | `compose.yaml` `cap_drop: [ALL]` | `smoke_test.sh` |
| 6 | `no-new-privileges` set | `compose.yaml` `security_opt:` | `smoke_test.sh` |
| 7 | **No host port published** — `expose` only | `compose.yaml` | `smoke_test.sh`, `verify_release.sh` |
| 8 | Health check defined and passing | `compose.yaml` + `Dockerfile` | `smoke_test.sh` |
| 9 | Restart policy `unless-stopped` | `compose.yaml` | `smoke_test.sh` |
| 10 | Container logs bounded (10 MB × 5) | `compose.yaml` `logging:` | `verify_release.sh` |
| 11 | Base image pinned by digest | `Dockerfile` `FROM …@sha256:` | `verify_release.sh` |
| 12 | Python dependencies pinned exactly | `requirements.txt` (`==`) | review |
| 13 | No secret in the image (file or env) | `.dockerignore`, `compose.yaml` `env_file` | `verify_release.sh` |
| 14 | No secret in the tree | — | `scripts/check_no_secrets.py` |
| 15 | Model artifact verified before every load | `src/inference.py` → `ml/verify_artifact.py` | `smoke_test.sh` |
| 16 | Passwords stored as Argon2id hashes, never plaintext | `src/security.py` | test suite |
| 17 | Session cookie `HttpOnly`/`Secure`/`SameSite`, XSRF + CORS enabled | `src/security.py`, `.streamlit/config.toml` | test suite |
| 18 | Uploads quarantined on the volume, size-capped, path-contained | `src/validation.py` | test suite |
| 19 | Database reachable only through the app (not a served static file) | Streamlit routing | `evidence/s11/probe_http.txt` |
| 20 | The tunnel is outbound-only; no inbound rule on the host | `cloudflared` service | `docs/architecture.md` §2 |

## 7. Rotating a secret

```bash
# edit the file in place (never echo the new value to a terminal)
$EDITOR .env && chmod 600 .env
docker compose up -d web                 # recreate so the new value is read
scripts/smoke_test.sh
```

Rotating `APP_SESSION_SECRET` invalidates every live session — that is the point of rotating it.
Rotating `INITIAL_ADMIN_PASSWORD` does **not** change an existing account: that variable seeds
accounts at first creation. Change a live password through the admin UI instead.

Rotating the tunnel token: replace `TUNNEL_TOKEN` in `.env.cloudflared`, then
`docker compose up -d cloudflared`. This is the operator's action, not the app's.

## 8. What this document does not authorise

- **No `cloudflared tunnel route` and no DNS change.** The ingress
  (`*aihubcampus.online → http://web:2026`) already exists and is operator-managed. Changing it
  is out of scope for this project.
- **No `docker compose down -v`.** It deletes the database volume. See `docs/runbook.md` §0.
- **No production/review/test stack outside the `aihubcampus` project.** This host runs other
  unrelated stacks; they are not ours to touch, restart or reconfigure.
- **No deployment without the gate.** `scripts/verify_release.sh` green, then deploy. A sprint
  is certified by its independent verification agent, not by this script.

## 9. Rollback

Application rollback and database rollback are different operations with different risk:

- **Application only** (the usual case): `git checkout <previous commit> && docker compose
  build web && docker compose up -d web && scripts/smoke_test.sh`. The volume is untouched.
- **Database**: `docs/runbook.md` §5c. Take a backup first, stop the service, restore with
  `--allow-live --yes`, start, smoke.

Both are rehearsed in `docs/runbook.md` §5 and `docs/runbook.md` §6.
