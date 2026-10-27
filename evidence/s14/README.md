# Sprint 14 evidence — report drafts, rubric matrix and the two checks over them

Sprint 14 has no runtime artefact. What it produces is documentation, so the evidence here is
the mechanical proof that the documentation is anchored to files that exist and numbers that
were recorded, plus an honest statement of what no script can prove.

## What is in this folder

| File | What it is |
|---|---|
| `check_report_refs.py` | Checks every repository path cited in `docs/report/*.md`, `docs/rubric_matrix.md` and `docs/report_evidence.md`; checks the 26 / 9 / 9 / 15 row counts; refuses a PASS claim on a line with no cited path; refuses a group-owned fact stated without "unconfirmed" |
| `check_report_refs.txt` | Its output at the committed tree: 29 documents, 925 paths checked, `RESULT: PASS`, exit 0 |
| `check_report_numbers.py` | Derives 47 figures from `models/metrics.json` and `models/eda/summary.json` and asserts each appears in the drafts exactly as recorded |
| `check_report_numbers.txt` | Its output: 47 of 47 found, `RESULT: PASS`, exit 0 |

Run both from the repository root:

```bash
python3 evidence/s14/check_report_refs.py
python3 evidence/s14/check_report_numbers.py
```

## What the two checks prove

1. **Every cited path exists.** 925 backticked repository paths across 29 documents resolve on
   disk. Six tokens were skipped, and the skip rule is narrow and visible:
   `ml/generate_eda.py --csv …` and `scripts/verify_release.sh --build --with-tests` and
   `scripts/smoke_test.sh --url …` (command lines, not paths), `ml/*.py`,
   `models/eda/01…06*.png` and `docs/report/*.md` (globs and ellipses). Nothing else was skipped.
2. **The numbers are the recorded numbers.** All 47 derived figures — held-out metrics, confusion
   cells, cross-validated means, split counts, class counts, artifact digest and size — appear in
   the drafts exactly as the artefact records them.
3. **No unsupported claim of success.** A line containing `PASS`, "all tests pass", "fully
   implemented" or "100% complete" must also cite a path on that line.
4. **Group-owned facts are not asserted.** "fourteen day", "four-member" and their variants must
   appear in a paragraph that marks them unconfirmed.
5. **The 26 components are present and numbered**, each with an H1 that carries its number.

## What they do not prove

- **That a cited file supports the sentence citing it.** The checks are structural. Reading each
  claim against its evidence is the gate's job, and no script replaces it.
- **Prose quality.** No human editor has read the drafts; that is the next step, not a completed
  one.
- **That the report is complete as a submission.** The cover page needs the group's names, IDs,
  course code and date, which this repository does not contain; the deck, script and Q&A bank are
  S15; the architecture diagram exists only as Mermaid source.

## Corrections these checks caught

The number check found one real error in a first draft of §12: the random forest's **held-out**
ROC-AUC was written as 0.7765, which is its cross-validated mean, not its held-out value of
0.7665. The draft was corrected in three places. This is the failure mode the check exists for —
a plausible figure typed from memory — and it is recorded rather than quietly fixed.

Two false positives in the reference check were also fixed in the checker, not by weakening it:
`PASS` matched inside "passes"/"bypass" until it was anchored as a whole word, and the
group-fact rule fired on a wrapped line until it was applied per paragraph rather than per line.

## Delivered in this sprint

| Path | Content |
|---|---|
| `docs/report/01_cover.md` … `26_appendices.md` | the 26 mandatory report components, drafted |
| `docs/report/00_figure_table_inventory.md` | 29 figures and 23 tables, each with its caption numbers and source file |
| `docs/rubric_matrix.md` | 26 components, rubric A (9 × 20 marks), rubric B (9 × 20 marks), 15 presentation topics, and what is still missing |
| `docs/report_evidence.md` §8–§18 | the S5–S13 evidence record, the final disposition of all 17 earlier-draft claims, and an extended file index |
