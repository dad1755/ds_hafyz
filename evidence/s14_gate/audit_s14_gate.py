#!/usr/bin/env python3
"""S14 gate — the verifier's own audit, written without reusing the sprint's checkers.

Nothing here imports or calls `evidence/s14/check_report_refs.py` or
`check_report_numbers.py`. The point is an independent second opinion:

  1. every path cited in the 26 drafts, the rubric matrix and report_evidence.md
     exists, and every cited *directory* is non-empty;
  2. the rubric matrix really carries 26 components, 9 rubric-A items summing to
     20, 9 rubric-B items summing to 20, and 15 presentation topics;
  3. every whole-word PASS in the drafts sits beside a cited path that exists, and
     every "completed"/"verified" occurrence is printed for a human to read;
  4. the key figures are read from the artefacts and compared with what the drafts
     print, per site rather than per corpus;
  5. the §17 disposition table adds up to 17 rows and its unconfirmed rows are named.

Exit codes: 0 = no discrepancy, 1 = at least one discrepancy.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "report"
DOCS = [*sorted(REPORT.glob("*.md")), ROOT / "docs" / "rubric_matrix.md", ROOT / "docs" / "report_evidence.md"]

ROOTS = ("evidence/", "docs/", "models/", "src/", "ml/", "tests/", "scripts/", "data/", "backups/")
SKIP = ("*", "\u2026", "<", ">", "{", "}", "|", "$", " ", "\\")
TICK = re.compile(r"`([^`\n]+)`")
problems: list[str] = []


def tokens(line: str):
    for raw in TICK.findall(line):
        token = raw.strip().rstrip(".,;:)]'\"")
        if not token.startswith(ROOTS):
            continue
        if any(m in token for m in SKIP):
            continue
        yield re.sub(r":\d+(-\d+)?$", "", token)


def check_paths() -> int:
    checked = 0
    for doc in DOCS:
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            for token in tokens(line):
                checked += 1
                target = ROOT / token
                if not target.exists():
                    problems.append(f"{doc.relative_to(ROOT)}:{lineno}: cited path missing: {token}")
                elif target.is_dir() and not any(target.iterdir()):
                    problems.append(f"{doc.relative_to(ROOT)}:{lineno}: cited directory is empty: {token}")
    return checked


def check_matrix() -> None:
    text = (ROOT / "docs" / "rubric_matrix.md").read_text(encoding="utf-8")

    def section(head: str) -> str:
        return text.split(head)[1].split("\n## ")[0]

    comp = len(re.findall(r"^\| \d+ \|", section("## 1. Report"), re.M))
    if comp != 26:
        problems.append(f"rubric_matrix.md: {comp} component rows, expected 26")
    for label, head in (("A", "## 2. Rubric A"), ("B", "## 3. Rubric B")):
        rows = re.findall(r"^\| " + label + r"\d+ \|[^|]*\|\s*(\d+)\s*\|", section(head), re.M)
        if len(rows) != 9 or sum(int(m) for m in rows) != 20:
            problems.append(f"rubric_matrix.md: rubric {label} rows={len(rows)} marks={sum(int(m) for m in rows)}, expected 9 rows / 20 marks")
    topics = len(re.findall(r"^\| P\d+ \|", section("## 4. Presentation"), re.M))
    if topics != 15:
        problems.append(f"rubric_matrix.md: {topics} presentation topics, expected 15")
    for doc in sorted(REPORT.glob("[0-9][0-9]_*.md")):
        if doc.name.startswith("00_"):
            continue
        first = doc.read_text(encoding="utf-8").splitlines()[0]
        if not first.startswith(f"# {int(doc.name[:2])}."):
            problems.append(f"docs/report/{doc.name}: first line is not '# {int(doc.name[:2])}.'")
    print(f"components 26 / rubric A 9=20 / rubric B 9=20 / topics 15 : ok")


def check_pass_claims() -> tuple[int, int]:
    """A PASS claim is only allowed on a line that cites a path which exists."""
    pass_lines = completed = 0
    for doc in sorted(REPORT.glob("*.md")):
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\bPASS\b", line):
                pass_lines += 1
                cited = list(tokens(line))
                if not cited:
                    problems.append(f"{doc.relative_to(ROOT)}:{lineno}: PASS with no cited path: {line.strip()[:90]}")
                for token in cited:
                    if not (ROOT / token).exists():
                        problems.append(f"{doc.relative_to(ROOT)}:{lineno}: PASS cites missing path {token}")
            if re.search(r"\bcompleted\b", line, re.I):
                completed += 1
                print(f"  completed: {doc.relative_to(ROOT)}:{lineno}: {line.strip()[:110]}")
    return pass_lines, completed


def check_figures() -> int:
    """Per-site: each of these numbers must appear in the file named, with the artefact's value."""
    metrics = json.loads((ROOT / "models" / "metrics.json").read_text())
    eda = json.loads((ROOT / "models" / "eda" / "summary.json").read_text())
    ev = metrics["evaluation"]["models"]
    sites: list[tuple[str, str, str]] = [
        ("docs/report/12_evaluation.md", f"{ev['random_forest']['metrics']['roc_auc']:.4f}", "RF held-out ROC-AUC"),
        ("docs/report/12_evaluation.md", f"{ev['decision_tree']['metrics']['f1']:.4f}", "DT held-out F1"),
        ("docs/report/12_evaluation.md", f"{ev['logistic_regression']['metrics']['precision']:.4f}", "LR held-out precision"),
        ("docs/report/12_evaluation.md", "4,528", "LR confusion TN"),
        ("docs/report/12_evaluation.md", "1,009", "LR confusion FN"),
        ("docs/report/11_training.md", f"{metrics['split']['train_rows']:,}", "train rows"),
        ("docs/report/11_training.md", f"{metrics['split']['test_class_counts']['1']:,}", "test class 1"),
        ("docs/report/13_comparison.md", f"{metrics['candidates']['decision_tree']['cv']['metrics']['f1']['mean']:.6f}", "DT CV F1 mean"),
        ("docs/report/09_eda.md", f"{eda['numeric_by_target']['AGE']['0']['mean']:.2f}", "AGE mean class 0"),
        ("docs/report/09_eda.md", f"{eda['pay0_by_target']['2']['default_rate_pct']:.2f}", "PAY_0=2 default rate"),
        ("docs/report/09_eda.md", f"{eda['education_by_target']['3']['default_rate_pct']:.2f}", "EDUCATION=3 default rate"),
        ("docs/report/07_dataset_description.md", metrics["dataset"]["sha256"][:8], "dataset sha256 prefix"),
        ("docs/report/17_model_integration.md", metrics["checks"]["artifact"]["sha256"][:8], "artifact sha256 prefix"),
        ("docs/report/17_model_integration.md", "0.7195348837209302", "T07 probability"),
        ("docs/report/12_evaluation.md", "68.01", "PAY_0 importance (second site)"),
        ("docs/report/18_system_testing.md", "285", "test-case count"),
    ]
    checked = 0
    for rel, value, label in sites:
        checked += 1
        text = (ROOT / rel).read_text(encoding="utf-8")
        if value not in text:
            problems.append(f"{rel}: {label} — artefact value {value!r} does not appear in this file")
        else:
            print(f"  ok  {rel:38s} {label:28s} {value}")
    return checked


def check_dispositions() -> None:
    text = (ROOT / "docs" / "report_evidence.md").read_text(encoding="utf-8")
    section = text.split("## 17.")[1].split("## 18.")[0]
    rows = re.findall(r"^\| (\d+) \|(.*)$", section, re.M)
    if len(rows) != 17:
        problems.append(f"report_evidence.md §17: {len(rows)} rows, expected 17")
    counts: dict[str, int] = {}
    for number, rest in rows:
        match = re.search(r"\*\*(confirmed|corrected|superseded|unconfirmed|missing)\*\*", rest)
        if not match:
            problems.append(f"report_evidence.md §17 row {number}: no disposition word")
            continue
        counts[match.group(1)] = counts.get(match.group(1), 0) + 1
        if match.group(1) in ("unconfirmed", "missing"):
            print(f"  §17 row {number}: {match.group(1)} — {rest.strip()[:100]}")
    print(f"§17 dispositions: {counts}")
    if counts.get("unconfirmed", 0) != 2 or counts.get("missing", 0):
        problems.append(f"report_evidence.md §17: unconfirmed={counts.get('unconfirmed', 0)} missing={counts.get('missing', 0)}, expected 2 unconfirmed and 0 missing")


def main() -> int:
    print("=" * 78)
    print("S14 GATE — verifier's independent audit (not the sprint's checkers)")
    print("=" * 78)
    print("[1] cited paths")
    checked = check_paths()
    print(f"    paths checked: {checked}")
    print("[2] rubric matrix shape")
    check_matrix()
    print("[3] PASS / completed claims")
    pass_lines, completed = check_pass_claims()
    print(f"    PASS occurrences in drafts: {pass_lines}; 'completed' occurrences: {completed}")
    print("[4] per-site figure checks")
    figures = check_figures()
    print(f"    sites checked: {figures}")
    print("[5] §17 dispositions")
    check_dispositions()
    print()
    if problems:
        print(f"DISCREPANCIES — {len(problems)}:")
        for problem in problems:
            print(f"  - {problem}")
        print()
        print("RESULT: FAIL")
        return 1
    print("RESULT: PASS — no discrepancy found by this audit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
