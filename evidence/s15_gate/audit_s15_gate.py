#!/usr/bin/env python3
"""S15 gate — the numbers, the demo table and the slide list, re-derived independently.

This is the acceptance gate's own audit. It does not import, call or trust
``evidence/s15/check_script_numbers.py``: every figure below is re-derived here from the
artefact that owns it, then looked for in ``docs/presentation_script.md`` at the rendering the
document uses.

Three things are audited:

1. **Figures.** Re-derived from ``models/metrics.json``, ``models/eda/summary.json``,
   ``models/model_manifest.json``, ``evidence/s4/feature_importances.txt`` and the rehearsal
   transcript. A figure that the deck states but no artefact supports is a FAIL.
2. **The demo table.** Row count, the planned-seconds column, the block duration §15.1 claims
   for it, and the ``ten steps`` wording — the document has to agree with its own table.
3. **Timing claims.** Every seconds value the deck prints is traced to the transcript (the
   recorded run) or to ``evidence/s15/README.md`` (an earlier attempt). Nothing else counts.

Read-only. Exit 0 only when every audit is clean.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECK = ROOT / "docs/presentation_script.md"
TRANSCRIPT = ROOT / "evidence/s15/demo_rehearsal.txt"
S15_README = ROOT / "evidence/s15/README.md"
METRICS = ROOT / "models/metrics.json"
EDA = ROOT / "models/eda/summary.json"
MANIFEST = ROOT / "models/model_manifest.json"
IMPORTANCES = ROOT / "evidence/s4/feature_importances.txt"

failures: list[str] = []
notes: list[str] = []


def ok(label: str, condition: bool, detail: str = "") -> None:
    print(f"{'PASS' if condition else 'FAIL'}  {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        failures.append(label)


def main() -> int:
    deck = DECK.read_text(encoding="utf-8")
    transcript = TRANSCRIPT.read_text(encoding="utf-8")
    s15_readme = S15_README.read_text(encoding="utf-8")
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    eda = json.loads(EDA.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    importances = IMPORTANCES.read_text(encoding="utf-8")

    ev = metrics["evaluation"]
    dt, rf, lr = (ev["models"][k] for k in ("decision_tree", "random_forest", "logistic_regression"))
    base = ev["baseline"]["metrics"]

    print("=" * 78)
    print("A. FIGURES — re-derived from the artefact, then looked for in the deck")
    print("=" * 78)

    def figure(label: str, value: str) -> None:
        ok(f"{label} = {value}", value in deck, "found in docs/presentation_script.md" if value in deck else "NOT IN DECK")

    figure("DT held-out accuracy (%.6f)" % dt["metrics"]["accuracy"], f"{dt['metrics']['accuracy']:.4f}")
    figure("DT held-out precision (%.6f)" % dt["metrics"]["precision"], f"{dt['metrics']['precision']:.4f}")
    figure("DT held-out recall (%.6f)" % dt["metrics"]["recall"], f"{dt['metrics']['recall']:.4f}")
    figure("DT held-out F1 (%.6f)" % dt["metrics"]["f1"], f"{dt['metrics']['f1']:.4f}")
    figure("DT held-out ROC-AUC (%.6f)" % dt["metrics"]["roc_auc"], f"{dt['metrics']['roc_auc']:.4f}")
    figure("RF held-out accuracy", f"{rf['metrics']['accuracy']:.4f}")
    figure("RF held-out F1", f"{rf['metrics']['f1']:.4f}")
    figure("LR held-out accuracy", f"{lr['metrics']['accuracy']:.4f}")
    figure("LR held-out ROC-AUC", f"{lr['metrics']['roc_auc']:.4f}")
    figure("baseline accuracy (%.6f)" % base["accuracy"], f"{base['accuracy']:.4f}")
    figure("accuracy delta over the constant answer", f"{dt['metrics']['accuracy'] - base['accuracy']:.4f}")

    cm = dt["confusion_matrix"]
    for key in ("tn", "fp", "fn", "tp"):
        figure(f"DT confusion {key.upper()}", f"{cm[key]:,}")
    figure("missed share of the 1,327 defaults", f"{cm['fn'] / (cm['fn'] + cm['tp']):.1%}")
    flagged = cm["tp"] + cm["fp"]
    figure("false positives among the flagged (%d)" % flagged, f"{cm['fp'] / flagged:.1%}")

    split = metrics["split"]
    figure("training rows", f"{split['train_rows']:,}")
    figure("held-out rows", f"{split['test_rows']:,}")
    for side in ("train_class_counts", "test_class_counts"):
        for cls, n in split[side].items():
            figure(f"{side}[{cls}]", f"{n:,}")

    cv = metrics["candidates"]
    figure("DT CV F1 mean", f"{cv['decision_tree']['cv']['metrics']['f1']['mean']:.4f}")
    figure("DT CV F1 std", f"{cv['decision_tree']['cv']['metrics']['f1']['std']:.4f}")
    figure("RF CV F1 mean", f"{cv['random_forest']['cv']['metrics']['f1']['mean']:.4f}")
    figure("LR CV F1 mean", f"{cv['logistic_regression']['cv']['metrics']['f1']['mean']:.4f}")
    for name in ("decision_tree", "random_forest", "logistic_regression"):
        figure(f"{name} CV ROC-AUC mean", f"{cv[name]['cv']['metrics']['roc_auc']['mean']:.4f}")
    figure("CV-vs-held-out F1 gap", f"{cv['decision_tree']['cv']['metrics']['f1']['mean'] - dt['metrics']['f1']:.4f}")

    figure("dataset rows", f"{metrics['dataset']['rows']:,}")
    figure("dataset columns", str(metrics["dataset"]["columns"]))
    figure("dataset sha256", metrics["dataset"]["sha256"])
    figure("class 0 count", f"{eda['class_counts']['0']:,}")
    figure("class 1 count", f"{eda['class_counts']['1']:,}")
    figure("class 0 share", f"{eda['class_share_pct']['0']:.2f}%")
    figure("class 1 share", f"{eda['class_share_pct']['1']:.2f}%")

    artifact = manifest["artifact"]
    figure("artifact sha256", artifact["sha256"])
    figure("artifact bytes", f"{artifact['bytes']:,}")

    figure("PAY_0 code 0 default rate", f"{eda['pay0_by_target']['0']['default_rate_pct']:.2f}%")
    figure("PAY_0 code 2 default rate", f"{eda['pay0_by_target']['2']['default_rate_pct']:.2f}%")
    figure("PAY_0 code 3 default rate", f"{eda['pay0_by_target']['3']['default_rate_pct']:.2f}%")
    figure("mean age class 0", f"{eda['numeric_by_target']['AGE']['0']['mean']:.2f}")
    figure("mean age class 1", f"{eda['numeric_by_target']['AGE']['1']['mean']:.2f}")
    figure("median LIMIT_BAL class 0", f"{eda['numeric_by_target']['LIMIT_BAL']['0']['median']:,.0f}")
    figure("median LIMIT_BAL class 1", f"{eda['numeric_by_target']['LIMIT_BAL']['1']['median']:,.0f}")
    figure("BILL_AMT1/BILL_AMT2 r", f"{eda['correlation_matrix']['BILL_AMT1']['BILL_AMT2']:.4f}")

    rows = {}
    for line in importances.splitlines():
        parts = line.split()
        if parts and parts[0].isupper() and len(parts) >= 3:
            try:
                rows[parts[0]] = float(parts[2])
            except ValueError:
                continue
    figure("PAY_0 importance share", f"{rows['PAY_0']:.2f}%")
    figure("PAY_2 importance share", f"{rows['PAY_2']:.2f}%")

    print()
    print("=" * 78)
    print("B. THE DEMO TABLE — the document against its own rows")
    print("=" * 78)

    step_rows = [l for l in deck.splitlines() if re.match(r"^\| \d+ \|", l)]
    ok("the demo table has rows", len(step_rows) > 0, f"{len(step_rows)} numbered rows")
    numbers = [int(l.strip("|").split("|")[0].strip()) for l in step_rows]
    ok("step numbers are 1..N with no gap", numbers == list(range(1, len(step_rows) + 1)), str(numbers))

    planned = 0
    for line in step_rows:
        cells = [c.strip() for c in line.strip("|").split("|")]
        m = re.match(r"^(\d+)\s*s$", cells[-2])
        if not m:
            failures.append(f"planned seconds unreadable in row {cells[0]}")
            print(f"FAIL  planned seconds unreadable in row {cells[0]}: {cells[-2]!r}")
        else:
            planned += int(m.group(1))
    print(f"INFO  the {len(step_rows)} rows plan {planned} s = {planned // 60} min {planned % 60} s in total")

    declared = re.search(r"^\| Live demo, (.+?) \| (\d+) min (\d+) s \|", deck, re.M)
    ok("§15.1 declares the demo block's plan", declared is not None)
    if declared:
        declared_steps = declared.group(1)
        declared_secs = int(declared.group(2)) * 60 + int(declared.group(3))
        print(f"INFO  §15.1 declares '{declared_steps}' at {declared_secs} s")
        ok(
            f"§15.1's step count matches the table ({len(step_rows)} rows)",
            str(len(step_rows)) in declared_steps or len(step_rows) == _word_to_int(declared_steps),
            f"§15.1 says '{declared_steps}', the table numbers 1..{len(step_rows)}",
        )
        ok(
            f"§15.1's planned duration matches the table's planned column ({planned} s)",
            declared_secs == planned,
            f"§15.1 says {declared_secs} s, the rows sum to {planned} s",
        )

    heading = re.search(r"^## 15\.3 The live demo — (.+)$", deck, re.M)
    ok("§15.3 heading names a step count", heading is not None)
    if heading:
        ok(
            "§15.3's heading step count matches the table",
            str(len(step_rows)) in heading.group(1) or len(step_rows) == _word_to_int(heading.group(1)),
            f"heading says '{heading.group(1)}', the table numbers 1..{len(step_rows)}",
        )

    for ref in sorted(set(re.findall(r"steps (\d+)[–-](\d+)", deck))):
        lo, hi = int(ref[0]), int(ref[1])
        ok(f"step reference '{ref[0]}–{ref[1]}' lies inside the table", hi <= len(step_rows), f"table ends at {len(step_rows)}")

    print()
    print("=" * 78)
    print("C. TIMING CLAIMS — every seconds value traced to a recorded artefact")
    print("=" * 78)

    transcript_secs = {float(v) for v in re.findall(r'"seconds":\s*([\d.]+)', transcript)}
    transcript_secs |= {float(v) for v in re.findall(r"first paint ([\d.]+)s", transcript)}
    total = re.search(r'"measured_total_seconds":\s*([\d.]+)', transcript)
    if total:
        transcript_secs.add(float(total.group(1)))
        summed = round(sum(float(v) for v in re.findall(r'"seconds":\s*([\d.]+)', transcript)), 1)
        ok("the transcript's per-step timings sum to its total", abs(summed - float(total.group(1))) < 0.05, f"{summed} vs {total.group(1)}")
    readme_secs = {float(v) for v in re.findall(r"([\d.]+) s", s15_readme)}

    # Only values the deck presents as *measured* are audited: the table's Rehearsed column and
    # the prose. The Planned column is a plan and needs no artefact.
    measured: dict[tuple[float, str], float] = {}
    for line in step_rows:
        cells = [c.strip() for c in line.strip("|").split("|")]
        cell = cells[-1]
        for value in re.findall(r"([\d.]+)\s*s\b", cell):
            measured[(float(value), f"row {cells[0]} rehearsed column")] = 0.05

    prose = "\n".join(l for l in deck.splitlines() if not l.startswith("|"))
    for minutes, seconds in re.findall(r"(\d+) min (\d+) s", prose):
        measured[(float(int(minutes) * 60 + int(seconds)), "prose (min s form, rounded)")] = 1.0
    prose = re.sub(r"\d+ min \d+ s", " ", prose)
    for value in re.findall(r"([\d.]+)\s*s\b", prose):
        measured.setdefault((float(value), "prose"), 0.05)

    for (value, where), tol in sorted(measured.items()):
        if any(abs(value - known) <= tol for known in transcript_secs):
            ok(f"{value} s ({where}) is in the rehearsal transcript", True)
        elif any(abs(value - known) <= tol for known in readme_secs):
            print(f"NOTE  {value} s ({where}) is not in the transcript; evidence/s15/README.md records it as an earlier attempt")
            notes.append(f"{value} s ({where}) supported only by evidence/s15/README.md, not the transcript")
        else:
            ok(f"{value} s ({where}) is supported by an artefact", False, "in NO evidence file — deck only")

    print()
    print("=" * 78)
    print("C2. CROSS-REFERENCES — every slide/section number the deck points at exists")
    print("=" * 78)

    slides = re.findall(r"^### Slide (\d+) — (.+)$", deck, re.M)
    slide_numbers = {int(n) for n, _ in slides}
    max_slide = max(slide_numbers) if slide_numbers else 0

    # §15.6's presenter table must point at slides that exist. This is where the fix commit
    # 26a33a8 went wrong: it renumbered the slides but left two rows citing the old numbers.
    presenter = re.search(r"^## 15\.6 .*?(?=^## )", deck, re.M | re.S)
    ok("§15.6 presenter table found", presenter is not None)
    row_titles: list[tuple[str, str]] = []
    if presenter:
        for line in presenter.group(0).splitlines():
            if not line.startswith("| ") or line.startswith("| Block") or set(line) <= set("|- "):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 2:
                row_titles.append((cells[0], cells[1]))
    ok("§15.6 has presenter rows", len(row_titles) >= 6, f"{len(row_titles)} rows")

    seen_slide_refs: dict[int, str] = {}
    for block, ref in row_titles:
        # §15.6 mixes two things in one column: slide ranges ("1–2", "8–9, steps 2–6") and step
        # ranges ("steps 7–10"). Only the slide ranges may be read as slide numbers — the Q&A row's
        # "1–8" is topics, not slides, and a "steps N–M" range is demo steps.
        slide_refs: set[int] = set()
        for chunk in ref.split(","):
            chunk = chunk.strip()
            if chunk.startswith("steps"):
                continue
            if "§" in chunk:
                continue
            for lo, hi in re.findall(r"(\d+)\s*[–-]\s*(\d+)", chunk):
                slide_refs.update(range(int(lo), int(hi) + 1))
            if re.fullmatch(r"\d+", chunk):
                slide_refs.add(int(chunk))
            elif re.match(r"^\d+\b", chunk) and not re.search(r"steps", chunk):
                slide_refs.add(int(re.match(r"^(\d+)", chunk).group(1)))
        for n in sorted(slide_refs):
            ok(
                f"§15.6 row '{block}' cites slide {n}, which exists",
                n in slide_numbers,
                f"deck has slides 1–{max_slide}" if n not in slide_numbers else "",
            )
        # The Q&A row leads the Q&A bank, not the slides; it must not be cross-checked for overlap.
        if "Q&A" not in block:
            for n in sorted(slide_refs & set(seen_slide_refs)):
                ok(
                    f"slide {n} is assigned twice in §15.6",
                    False,
                    f"'{seen_slide_refs[n]}' and '{block}'",
                )
            for n in slide_refs:
                seen_slide_refs.setdefault(n, block)

    missing = sorted(set(range(1, max_slide + 1)) - set(seen_slide_refs))
    ok("every slide has a presenter block in §15.6", not missing, f"unassigned: {missing}" if missing else "")

    # Prose references of the form "slide 11" must land on the slide the text is talking about.
    for ref in sorted({int(n) for n in re.findall(r"slide (\d+)\b", deck)}):
        ok(f"prose reference 'slide {ref}' points at an existing slide", ref in slide_numbers, f"deck has 1–{max_slide}")

    section_heads = {m.group(1) for m in re.finditer(r"^## 15\.(\d+)", deck, re.M)}
    section_heads |= {f"3.{m.group(1)}" for m in re.finditer(r"^### 15\.3\.(\d+)", deck, re.M)}
    for ref in sorted(set(re.findall(r"§15\.(\d+(?:\.\d+)?)", deck))):
        ok(f"cross-reference §15.{ref} exists", ref in section_heads, f"sections found: {sorted(section_heads)}")

    print()
    print("=" * 78)
    print("D. SLIDE LIST — the blueprint §9 S15 order against the deck's slides")
    print("=" * 78)
    ok("the deck has twelve slides", len(slides) == 12, f"{len(slides)} slides")
    titles = " || ".join(t for _, t in slides).lower()
    required = [
        ("problem", ["problem"]),
        ("objectives", ["objective"]),
        ("dataset", ["dataset"]),
        ("preprocessing", ["preprocessing"]),
        ("EDA", ["eda"]),
        ("ML models / split", ["methodology", "split"]),
        ("comparison / confusion matrix", ["comparison", "confusion"]),
        ("architecture", ["architecture"]),
        ("Admin demo", ["admin"]),
        ("User prediction demo", ["user prediction", "prediction demo", "user demo"]),
        ("ethics / limitations", ["ethics", "limitation"]),
        ("conclusion / improvements", ["conclusion"]),
    ]
    for topic, keys in required:
        hit = any(k in titles for k in keys)
        ok(f"blueprint slide topic present: {topic}", hit, "matched a slide title" if hit else "NO slide covers this topic")

    print()
    print("=" * 78)
    print("E. THE HONESTY CLAIMS THAT ARE CHECKABLE IN CODE")
    print("=" * 78)

    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    ok("no published host port (expose only)", "expose:" in compose and "ports:" not in compose)
    ok("read-only root filesystem", "read_only: true" in compose)
    ok("all capabilities dropped", "cap_drop:" in compose and "- ALL" in compose)
    ok("manifest records the artifact as uncalibrated", "uncalibrated" in json.dumps(manifest))
    ok("held-out rows took no part in selection", metrics["selection"]["test_rows_used_for_selection"] == 0)
    train = (ROOT / "ml/train.py").read_text(encoding="utf-8")
    ok("the deck's max_depth=5 / random_state=42 is what trains the tree", 'max_depth": 5' in train and "SEED = 42" in train)
    ok("no class weights anywhere in ml/ or src/", not _grep(ROOT / "ml", "class_weight") and not _grep(ROOT / "src", "class_weight"))
    security = (ROOT / "src/security.py").read_text(encoding="utf-8")
    ok("passwords are Argon2id", "argon2id" in security.lower() and "PasswordHasher" in security)
    predictions = (ROOT / "src/predictions.py").read_text(encoding="utf-8")
    ok("history is scoped by user_id in SQL", "WHERE user_id = ?" in predictions)

    print()
    print("=" * 78)
    print(f"RESULT: {'PASS' if not failures else 'FAIL'} — {len(failures)} failing audit(s)")
    if notes:
        for note in notes:
            print(f"  note: {note}")
    for failure in failures:
        print(f"  failure: {failure}")
    print("=" * 78)
    return 0 if not failures else 1


_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
          "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15}


def _word_to_int(text: str) -> int | None:
    for word, value in _WORDS.items():
        if re.search(rf"\b{word}\b", text.lower()):
            return value
    return None


def _grep(directory: Path, needle: str) -> bool:
    for path in directory.rglob("*.py"):
        if needle in path.read_text(encoding="utf-8", errors="ignore"):
            return True
    return False


if __name__ == "__main__":
    sys.exit(main())
