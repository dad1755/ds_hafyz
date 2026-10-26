# S10 evidence — admin model evaluation and insight panels

Everything here is real command output captured on ridergami2 on 2026-10-27 against the
committed tree. Each `.sh` file prints the command it ran before its output, and each `.py`
probe exits non-zero when a check fails, so none of this can pass by printing a sentence.

| File | What it shows |
|---|---|
| `trace_metrics.txt` | The card's headline acceptance: **every displayed number traced to `metrics.json`**. The probe builds two independent renderings of the same facts — the rows `src.evaluation` returns (what the page draws) and the values read straight out of `metrics.json` with `json` (what the file says) — and diffs them with `difflib`. Result: `39 lines identical` for the comparison table, `15 lines identical` for the confusion matrices, every metadata field `equal`, `RESULT: PASS … 0 mismatches`. |
| `pytest_s10.txt` | The 15 Sprint 10 tests, all `PASSED`. They include the mutation test (rewrite a copy of `metrics.json`, re-render, the page follows the file), the cell-position test (TN/FP must sit on the row labelled actual class 0), and the refusal tests. |
| `pytest_all.txt` | The whole suite in the built image: `262 passed` (247 at S9 + 15). |
| `restart.txt` | The restart the card asks for: the deployed container is recreated (`started=…20:08:10Z`, health `healthy`, image `9144745f24e5`), `/_stcore/health` → `ok`, no published host port, the ten figure artifacts listed **from inside the running container**, and then a full render in that container: `11 figures, 6 tables, 0 errors, 0 warnings`, rendered accuracy `0.817167` equal to `metrics.json`, rendered `TN/FP/FN/TP (4431, 242, 855, 472)` equal to `metrics.json`, and a user session refused (`0 figures`, `0 tables`, audited). |
| `draft_grep.txt` | **No v3 draft statistic is hard-coded.** All 20 draft figures searched across `app.py` and `src/`: `no match`. The same numbers are then shown where they legitimately live — `docs/report_evidence.md` (whose own words label both drafts *draft, not proof*) and `evidence/s0/draft_v3_extracted.txt` — beside the record's real counts, which differ (the draft asserts TN 4,432 / FP 241 / FN 856 / TP 471 for the decision tree; the record holds 4,431 / 242 / 855 / 472). |
| `browser_check.txt` + `evaluation_*.png` | A real Chromium (`mcr.microsoft.com/playwright:v1.55.0-noble`) driving a throwaway container of `aihubcampus-web:s10` at 375×812 and 1280×800: sign in, open **Model evaluation**, every section present, `11` figures decoded (`naturalWidth > 0`), zero horizontal overflow at all three scroll positions, and the record's `metrics.json` SHA-256 on screen. Then a second sign-in as a **user**: nav is `Home / Predict default risk / My prediction history` — no evaluation entry — and no evaluation content renders. Screenshots: `evaluation_375px_top.png`, `_confusion.png`, `_metadata.png`, the desktop trio, and `evaluation_user_nav.png`. |
| `build.txt` | The image build (`aihubcampus-web:local` = `aihubcampus-web:s10` = `9144745f24e5`) and the figure artifacts present in it — the six EDA PNGs plus `summary.json`, and the four `models/figures` PNGs. Before this sprint those directories were excluded by `.dockerignore`, so the page would have warned that six figures were absent from the build. |

## Two defects found and fixed while producing this evidence

1. **The confusion matrix was drawn upside down.** The cell at row 0 was painted at `y=1` while
   the tick at `y=1` was labelled `1 = default`, so TN (4,431) and FP (242) appeared on the
   *actual = 1* row. Every count was still correct, so a "the numbers are on screen" check
   passed. `test_each_confusion_matrix_puts_its_cells_on_the_row_and_column_they_belong_to`
   now reads each cell's position off the artists and compares it with the tick label there.
2. **The comparison table's `threshold` column mixed floats with prose.** The constant-answer
   baseline records its threshold as a sentence, so Streamlit fell back from Arrow to JSON on
   every render (`ArrowInvalid: Could not convert 'not applicable …'`). The column is now
   formatted as text for every row.

## Re-running the checks

```bash
# 1. build, then the gate in the image
docker build -t aihubcampus-web:local -t aihubcampus-web:s10 .
docker run --rm -e PYTHONPATH=/app -v "$PWD:/app:z" -w /app aihubcampus-web:s10 \
    python -m pytest tests/test_evaluation.py -v

# 2. the trace: page rows vs metrics.json, with a diff
docker run --rm -e PYTHONPATH=/app -v "$PWD:/app:z" -w /app aihubcampus-web:s10 \
    python evidence/s10/trace_metrics.py

# 3. the draft-statistics search
bash evidence/s10/draft_grep.sh

# 4. deploy, restart, and render inside the restarted container
bash evidence/s10/restart.sh

# 5. the browser run (throwaway container, synthetic accounts, cleans up after itself)
bash evidence/s10/run_ui_check.sh
```

## One honest note about `browser_check.txt`

The comparison table and the metadata panel are Streamlit **dataframe** grids, drawn on a
canvas, so their cell values are not in `document.body.innerText`; the browser run therefore
asserts the section headings, the captions and the figure count, not the table cells. The cell
values are covered twice elsewhere: `trace_metrics.txt` (page rows vs the file) and
`pytest_s10.txt` (`test_the_page_follows_the_record_when_the_record_changes`,
`test_the_rendered_page_shows_all_eleven_figures_and_no_warning`). The screenshots show the
values on screen.

No password, token or hash value appears in any file here. The browser run generates both
synthetic passwords in-process (`openssl rand`) and never writes them; its `secret_sweep`
reports `0` for each.
