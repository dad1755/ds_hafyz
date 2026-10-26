# S9 evidence — admin dataset manager (staged dataset vs deployed model)

Everything here is real command output captured on ridergami2 on 2026-10-26/27 against the
committed tree. Re-run any file's command from the repository root; the `.sh` files print the
command they ran before its output.

| File | What it shows |
|---|---|
| `pytest_s9.txt` | `pytest tests/test_admin.py -v -k …` — the 20 Sprint 9 tests, all `PASSED`. |
| `pytest_all.txt` | The whole suite in the built image: `247 passed`. |
| `probe_datasets.txt` | The service layer, end to end, in the image: the seed stages with **30,000 records × 25 columns, class 0 = 23,364, class 1 = 6,636** and SHA-256 `a0f0ab49…` (the manifest's own dataset checksum); the preview is 25 aggregate rows and carries no record; **two malformed uploads refused**, each with its codes and reason quoted; the rejection log; the activation; the pointer surviving a new connection *and* a second startup; and the model artifact SHA-256 `48ce02563b2aad9f…` **identical before and after**. |
| `browser_check.txt` + `dataset_*.png` | A real Chromium (`mcr.microsoft.com/playwright:v1.55.0-noble`) driving a throwaway container of `aihubcampus-web:s9` at 375×812 and 1280×800: sign in, open Dataset manager, stage a 400-row upload, activate it, then upload a CSV with `PAY_6` removed and read the refusal. Zero horizontal overflow at every step; neither the synthetic password nor any `$argon2` hash appears in the rendered text. Screenshots: `initial`, `staged`, `activated`, `rejected` (phone) and `initial` (desktop). |
| `container_probe.txt` | The **deployed** container (`aihubcampus-web-1`, image `6908282833ac`, healthy): its own `dataset_versions` row (version 1 = the seed, active, 30,000 / 23,364 / 6,636, SHA-256 `a0f0ab49…`), the same checksum in `/app/models/model_manifest.json`, the quarantine directory writable on the volume, the seed present as a read-only mount, `/_stcore/health` → `ok`, and no published host ports. |
| `hygiene.txt` | AST import/method inventory of `src/data_manager.py` and `src/pages_datasets.py`: no training or serialisation import, no `fit`/`predict`/`dump`/`load` call — plus `scripts/check_no_secrets.py`: `PASS`. |
| `build.txt` | The image build (`aihubcampus-web:local` = `aihubcampus-web:s9` = `6908282833ac`), the pinned tag set, the compose config showing the read-only seed mount, `APP_QUARANTINE_DIR` on the volume, and 0 published host ports. |
| `deploy_first_visit.txt` | The first real page load of the deployed app after the rebuild — the visit that makes the app run its own startup work (migration `0003_dataset_staging`, seed registered as version 1). |

## Re-running the checks

```bash
# 1. build, then run the gate in the image
docker build -t aihubcampus-web:local -t aihubcampus-web:s9 .
docker run --rm -v "$PWD:/app:z" -w /app aihubcampus-web:s9 python -m pytest tests -q

# 2. the service-layer probe (staging counts, rejections, activation, artifact hashes)
docker run --rm -v "$PWD:/app:z" -w /app aihubcampus-web:s9 python evidence/s9/probe_datasets.py

# 3. the browser run (throwaway container, synthetic administrator, cleans up after itself)
bash evidence/s9/run_ui_check.sh > evidence/s9/browser_check.txt 2>&1

# 4. the deployment's own state
bash evidence/s9/container_probe.sh > evidence/s9/container_probe.txt 2>&1
```

## One honest note about `browser_check.txt`'s `checks` block

The JS records a few `false` flags whose text lives **inside a dataframe grid**, which Streamlit
renders on a canvas: `document.body.innerText` does not carry those cells, so
`deployed_dataset_sha_shown`, `counts_quoted` and `rejection_in_log_table` read `false` even
though the values are on screen — the checksum `a0f0ab49…`, the 400 / 306 / 94 counts and the
`missing_pay6.csv` rejection row are all visible in `dataset_*_initial.png`,
`dataset_375px_staged.png` and `dataset_375px_rejected.png`, and the same strings are asserted
programmatically by the AppTest tests in `pytest_s9.txt`
(`test_the_page_separates_the_deployed_dataset_from_the_staged_one`,
`test_the_page_stages_an_upload_and_shows_counts_but_no_row`,
`test_the_page_lists_a_rejection_with_the_reason_it_was_refused`). Everything else in that block
is a direct text assertion on the rendered page.

No password, token or hash value appears in any file here. The browser run generates its
synthetic administrator password in-process (`openssl rand`) and never writes it.
