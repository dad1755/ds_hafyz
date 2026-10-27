# evidence/s15 — the demo rehearsal and the numbers check

Sprint 15 produces documentation plus one runtime artefact: a rehearsal. Everything in this folder
was produced by a command run against the live deployment on ridergami2 and the files it wrote; no
output here is transcribed by hand.

## What is in this folder

| File | What it is | How it was produced |
|---|---|---|
| `demo_rehearsal.txt` | The recorded rehearsal of the demo script against `https://www.aihubcampus.online`: 33 checks, 0 failed, `verdict: PASS`, 96.7 s of measured on-screen time, plus the per-step timings and the two observations the browser could make. | `SCRATCH_DIR=<private dir> REHEARSAL_ROWS=550 bash evidence/s15/run_demo_rehearsal.sh > evidence/s15/demo_rehearsal.txt 2>&1` |
| `s15_01_signin.png` … `s15_09_model_evaluation.png` | One screenshot per demo step, from the same run: sign-in, administrator home, user management, the rejected upload, the staged upload, the filled form, the scored result, the refused submission, the evaluation page. | written by `ui_demo_rehearsal.js` |
| `ui_demo_rehearsal.js` | The browser journeys: administrator sign-in, user management, dataset validation (one refusal, one acceptance), user sign-in, the 23 preset values, the scored result, the refused submission, the history check, model evaluation, sign-out. Talks only to the public hostname. | Playwright + Chromium, `node evidence/s15/ui_demo_rehearsal.js` |
| `run_demo_rehearsal.sh` | Driver: re-arms a synthetic administrator, builds the two CSVs, runs the browser, deactivates the administrator (always, via the `EXIT` trap). | — |
| `make_demo_admin.py` / `deactivate_demo_admin.py` | Insert and deactivate the synthetic administrator. The password arrives in the environment, is hashed with the application's own `security.hash_password`, and is never printed. | `docker compose exec -T … web python - < …` |
| `make_demo_uploads.py` | Writes the two uploads from the seed dataset: 25 columns in documented order (must be accepted) and the same rows with `PAY_AMT6` removed (must be refused). | `python3 evidence/s15/make_demo_uploads.py <dir> 550` |
| `check_script_numbers.py` | 82 figures: re-derived from `models/metrics.json`, `models/eda/summary.json`, `models/model_manifest.json` and `evidence/s4/feature_importances.txt`, and read back out of the rehearsal transcript for the demo's promised results. Each must appear in `docs/presentation_script.md`. | `python3 evidence/s15/check_script_numbers.py` |
| `check_script_numbers.txt` | Its output: `RESULT: PASS — 82 of 82 figures found, exit 0`. | as above |

## Why a synthetic administrator

The demo script's first steps are administrator steps. The operator's account (`ds_hafyz`) belongs
to the operator, and this sprint must not rewrite its credential — so the rehearsal drives the
administrator pages with `s15_demo_check`, created for the run and deactivated at the end of it.
The account is deactivated, not deleted, so the audit trail survives; its password is generated per
run, lives in a mode-600 file under the scratch directory, and is removed by the driver's trap.

**On demo day the presenter uses the operator's administrator account.** Confirm its password
before the session; nothing in this folder needs to know it.

## Repeat runs and the two duplicate paths

`REHEARSAL_ROWS` exists because the dataset manager rejects identical bytes by checksum. A repeat
run with a row count that has already been staged correctly answers *Those exact bytes are already
version #N — nothing new was staged*, and the driver reports that as a pass. Likewise, scoring the
same 23 values twice from the same session is recognised and not logged twice. Both are correct
behaviour and both are documented in `docs/presentation_script.md`; neither is a failure of the
rehearsal.

## Flakiness, recorded rather than smoothed

The recorded run needed no retry. Earlier attempts did, and they are why the driver has the retries
it has:

- one attempt measured a **32.4 s** first paint and then found no sign-in input within 30 s — the
  driver now waits for the input itself and reloads once;
- one attempt died on `net::ERR_NETWORK_CHANGED` before the first paint — the driver retries the
  first navigation once;
- two attempts pressed *Validate and stage* before a 27 KB upload had crossed the tunnel and were
  answered *Choose a CSV file first* — a correct answer to a premature click, so the driver now
  retries the button until the page reports an outcome;
- one attempt read the evaluation page while it was still painting and saw 5 of 6 sections — the
  driver now waits for the last heading.

## What this evidence does not claim

- **It is the implementer's own record.** A sprint is VERIFIED by its independent gate, not here.
- **It does not claim a rehearsed presentation.** The demo was rehearsed; the speaking was not, and
  the timing in `docs/presentation_script.md` is a planning assumption, not an assessment limit.
- **It does not read the data grids.** The comparison table, the confusion matrices and the
  per-upload fact table are `st.dataframe` grids whose cells are painted, not DOM text, so the
  transcript asserts the prose the page writes from the same metrics and that the grids paint. The
  figures themselves are checked against `models/metrics.json` by `check_script_numbers.py`.
- **It does not prove the demo cannot drift.** It records the commit it ran at (`HEAD` in the
  transcript header), so drift between now and the session is detectable rather than invisible.
- **It wrote to the live database.** One prediction row for `demo_user`, one rejected upload, one
  staged (inactive) dataset version. It did not change the deployed model, the active dataset, or
  the operator's credential.

## Reproducing

```bash
SCRATCH_DIR=<private dir> REHEARSAL_ROWS=550 bash evidence/s15/run_demo_rehearsal.sh \
  > evidence/s15/demo_rehearsal.txt 2>&1
python3 evidence/s15/check_script_numbers.py
```

`SCRATCH_DIR` must be a private directory (the driver creates the credential file mode-600 inside
it) and `NODE_MODULES` must point at a tree with Playwright installed — the default is
`/home/ec-user/qa759-v2/node_modules`.
