# S16 evidence — production release, audit and handover

Every file here is a verbatim command transcript, captured on `ridergami2` against the live
`aihubcampus` Compose project and the public URL. Nothing is retyped from memory, and no number in
`docs/RELEASE_NOTES.md` or `docs/runbook.md` is quoted from anywhere else. Where a check is a
*negative* (a refused upload, a refused restore target), the refusal itself is the evidence.

The release tag is `v1.0.0`. Each script below is committed next to its transcript, so the release
can be re-proved rather than re-read.

| File | What it is | Reproduce with |
|---|---|---|
| `preflight.txt` | what is serving, and whether it is this tree: container id, image id, hardening flags, **30/30 application `.py` files byte-identical between the image and the checkout**, artifact/manifest hashes, live DB row counts | `bash evidence/s16/preflight.sh` |
| `release_gate_attempt.txt` | `scripts/verify_release.sh` on a **clone of the tag** — the release tree, plus the two operator-supplied files, nothing else. **This run did not complete**: 11 checks passed, then `docker run` stalled because the host's Docker daemon had stopped creating containers under load. It is kept as the record of the attempt, with a note at the top; the gate must be re-run | `TAG=v1.0.0 bash evidence/s16/release_gate.sh` |
| `smoke_test.txt` | `scripts/smoke_test.sh --url …`: the running stack's hardening checks and the public HTTPS surface | `scripts/smoke_test.sh --url https://www.aihubcampus.online` |
| `backup_restore_drill.txt` | a consistent backup taken **outside the live volume**, a second copy, and a restore into a **disposable** volume: checksum, `integrity_check`, every table count, then the drill volume removed | `BACKUP_OUT=<dir outside the volume> bash evidence/s16/backup_restore_drill.sh` |
| `rollback_drill.txt` | `docker compose down` **without `-v`** → the volume survives → `up -d` → healthy on a new container id, database sha256 and row counts identical, public HTTPS back | `TAG=v1.0.0 bash evidence/s16/rollback_drill.sh` |
| `live_smoke.txt` | HTTPS probe, the artifact's own probability computed **two independent ways**, then both roles end to end through the live URL in a real Chromium, with the on-screen probability compared to the artifact's | `bash evidence/s16/run_release_smoke.sh` |
| `s16_01_signin.png` … `s16_09_invalid_input.png` | one screenshot per browser step, written by that same run | — |
| `*.sh`, `ui_release_smoke.js` | the scripts that produced the transcripts above | — |

## What each release gate maps to

| Gate (blueprint §11) | Where |
|---|---|
| **A — academic data** | `preflight.txt` (dataset sha256 `a0f0ab49…`, 30,000 × 25, class counts), `release_gate_attempt.txt` (the image and artifact checks that ran before the stall), `docs/model_card.md` §4 |
| **B — ML** | `live_smoke.txt` (both computations of P(class 1) = `0.7195348837209302`), `docs/model_card.md` §5 (three algorithms, held-out metrics, confusion matrix, the 0.3557 recall) |
| **C — app** | `live_smoke.txt`: 23 inputs, probability, band, advice, CSV manager, and the result coming from the artifact rather than a table |
| **D — quality** | `live_smoke.txt` (invalid CSV, empty field, no hash on screen), `smoke_test.txt` (hardening checks on the running container), `rollback_drill.txt` (restart persistence), and the suite evidence named below |
| **E — public release** | `live_smoke.txt` (HTTPS, `server: cloudflare`, no host port), `backup_restore_drill.txt`, `rollback_drill.txt` |
| **the gate script itself** | `release_gate_attempt.txt` — incomplete at S16 (host Docker stall); the complete run in this sprint was at `08365e8`, 24 passed / 1 failed on the two evidence files that did not exist yet |
| **F — submission** | `docs/RELEASE_NOTES.md`, `docs/model_card.md`, `docs/runbook.md` §10, `docs/acceptance/` (S00–S15), `docs/test_matrix.md` |

## The test suite — where its evidence is, and why it is not re-run here

No application code has changed since the S13 gate ran the suite:

```console
$ git diff --stat 49540a6..HEAD -- '*.py' requirements.txt requirements.in Dockerfile compose.yaml .streamlit/
 evidence/s14/check_report_numbers.py  |  97 +++++++++
 evidence/s14/check_report_refs.py     | 180 +++++++++++++
 evidence/s15/check_script_numbers.py  | 177 ++++++++++++++++
 evidence/s15/make_demo_admin.py       |  69 ++++
 … (only evidence/ helper scripts — no src/, ml/, app.py, dependency or container change)
```

The suite's last full run is `evidence/s11/` (285 tests) and the S12/S13 gate transcripts; the
command to re-run it is:

```bash
docker run --rm --network none -v "$PWD:/app:z" -w /app aihubcampus-web:local \
    python -m pytest tests -q -p no:cacheprovider
```

S16 attempted it twice and both runs were killed under host memory pressure (swap exhausted by a
concurrent build on this host, not by the suite), so no transcript of a completed run is claimed
here. `preflight.txt` is what makes the omission safe: the running image's application code is
byte-identical to this tree, so the S13-gate result applies to the tree this release ships.

## Notes on method

- **The gate runs on a clone of the tag, not on the working checkout.** The checkout is shared
  with another project on this host and carries one untracked file that belongs to it. A clone of
  `v1.0.0` plus `.env` and the seed CSV *is* the release tree — that is also the reproducibility
  claim, so the gate measures it.
- **The gate is run without `--build`**, so it cannot retag the image that is currently serving.
  The build path is already evidenced in `evidence/s12/fresh_clone.txt` (a fresh clone builds and
  serves) and `evidence/s13/build.txt`; `preflight.txt` closes the loop by proving the running
  image's application code is byte-identical to the tree.
- **The rollback drill restarts the real stack.** It is the documented path (`down`, never `-v`),
  run once, with the database sha256 on both sides. The live URL was probed immediately afterwards
  and again by the full browser smoke, so the evidence that follows the restart describes the
  post-restart deployment.
- **The backup never touches the live volume.** The snapshot is a `VACUUM INTO` taken inside the
  container and streamed out; the destination is a directory on the host, `chmod 700`, and a second
  copy is made beside it. The restore target is a disposable volume that is deleted at the end.
- **The synthetic administrator** used for the admin journey is created for the run and
  deactivated after it; the operator's `ds_hafyz` credential is never rewritten and never read.
  The transcript shows the deactivation.
- **Nothing secret is printed.** The `.env` values are never echoed, hashed or passed on a command
  line; the synthetic password lives in a mode-600 scratch file and is deleted by the run's trap.
