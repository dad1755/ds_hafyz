# evidence/s13 — the public HTTPS surface

Sprint 13 deliverable (blueprint §9 SPRINT 13, §7 network rule). Every file here was produced by a
command run against the live deployment on ridergami2; none of it is transcribed by hand.

| File | What it proves | How it was produced |
|---|---|---|
| `browser_check.txt` | Three browser journeys — operator admin, synthetic admin, demo user — through `https://www.aihubcampus.online`: sign-in, XSRF cookie, WebSocket, prediction, history, user management, CSV upload and staging, model evaluation, refresh, sign-out. 29 checks, verdict `PASS`. | `bash evidence/s13/run_ui_tunnel.sh > evidence/s13/browser_check.txt` |
| `probe_http.py` output (`probe_http.txt`) | Protocol level: XSRF cookie flags, CORS does not trust a foreign origin, WS `101` from the real origin and `403` from a foreign one, the SQLite database and the model artifact are not downloadable, apex hostname behaves the same. | `python3 evidence/s11/probe_http.py https://www.aihubcampus.online` |
| `smoke_test.txt` | The running stack is the hardened stack (non-root, read-only rootfs, no capabilities, no host ports, one writable mount) **and** the public surface answers 200. | `bash scripts/smoke_test.sh --url https://www.aihubcampus.online` |
| `check_no_secrets.txt` | No operator secret and no credential pattern in any tracked file. | `python3 scripts/check_no_secrets.py` |
| `tunnel_signin.png` | The sign-in form as served over HTTPS by the Cloudflare edge. | Playwright screenshot |
| `tunnel_operator_forced_change.png` | The operator admin (`ds_hafyz`) lands on the forced password-change screen — `must_change_password=1` by design (D13). The password was **not** changed. | Playwright screenshot |
| `tunnel_admin_home.png` | Signed in as the synthetic admin, six navigation sections. | Playwright screenshot |
| `tunnel_prediction_result.png` | A scored prediction through the tunnel: probability, band, threshold, model version. | Playwright screenshot |
| `tunnel_dataset_staged.png` | A 500-row CSV uploaded through the browser and staged as dataset version #2, explicitly not activated. | Playwright screenshot |
| `tunnel_evaluation.png` | The model evaluation page, all six sections, figures painted. | Playwright screenshot |
| `tunnel_user_home.png`, `tunnel_user_prediction.png` | The demo user's three-section navigation and a scored prediction. | Playwright screenshots |

## Reproducing

```bash
bash evidence/s13/run_ui_tunnel.sh        # needs SCRATCH_DIR, a private directory, and node+playwright
```

## Scripts

| Script | Purpose |
|---|---|
| `run_ui_tunnel.sh` | Driver: re-arms a synthetic admin, builds the upload CSV, runs the browser, deactivates the admin (always). |
| `ui_tunnel.js` | The Playwright journeys. Talks only to the public hostname. |
| `make_synth_admin.py` | Inserts (or re-arms) the synthetic admin. Password comes from the environment, is hashed, is never printed. |
| `deactivate_synth_admin.py` | Deactivates that account afterwards — deactivation, not deletion, so the audit trail survives. |
| `make_upload_subset.py` | Writes the 500-row CSV prefix the dataset manager uploads. |

## Why a synthetic administrator

`ds_hafyz` is seeded with `must_change_password = 1` (its operator-chosen password is deliberately
weak, docs/architecture.md D13), so its first sign-in can only reach the password-change screen.
Driving the administrator pages therefore needs a usable account — and the operator's credential
must not be rewritten. The synthetic account (`s13_tunnel_check`) is created for the run and
deactivated at the end of it; its password is generated per run, lives in a mode-600 file under the
scratch directory, and is deleted by the driver's `EXIT` trap.

## What this evidence does not claim

- It is the implementer's own record. A sprint is VERIFIED by its independent gate, not by this
  directory.
- The screenshots show usernames (`ds_hafyz`, `demo_user`) because the user-management page lists
  accounts. No password and no tunnel token appears in any file here — `check_no_secrets.txt` and
  the driver's redaction are the mechanical proof.
