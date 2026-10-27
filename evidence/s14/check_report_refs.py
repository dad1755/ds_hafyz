#!/usr/bin/env python3
"""Check that the report drafts and the rubric matrix point at files that exist.

What it proves, and what it does not:

  * every repository path cited in `docs/report/*.md`, `docs/rubric_matrix.md` and
    `docs/report_evidence.md` exists on disk (globs, ellipses and `<placeholders>` are
    skipped by a stated rule, never silently);
  * the 26 mandatory report components each have a draft file, and the rubric matrix
    counts 26 / 9 / 9 / 15 rows;
  * no draft claims PASS / "all tests pass" / "fully implemented" on a line that does not
    also cite an evidence path;
  * the group-owned facts (schedule, member split) are never stated without being marked
    unconfirmed.

It does not check that a cited file *supports* the sentence citing it. That is the gate's
job, and no script can replace it.

Exit codes: 0 = all checks pass, 1 = at least one check failed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "docs" / "report"
DOCS = [
    *sorted(REPORT_DIR.glob("*.md")),
    ROOT / "docs" / "rubric_matrix.md",
    ROOT / "docs" / "report_evidence.md",
]

PATH_ROOTS = ("evidence/", "docs/", "models/", "src/", "ml/", "tests/", "scripts/", "data/", "backups/")
SKIP_MARKERS = ("*", "\u2026", "<", ">", "{", "}", "|", "$", " ", "\\")
TICK = re.compile(r"`([^`\n]+)`")
TRAILING = ".,;:)]'\""
BANNED = (re.compile(r"\bPASS\b"), re.compile(r"all tests pass", re.I),
          re.compile(r"fully implemented", re.I), re.compile(r"100% complete", re.I))
GROUP_FACTS = ("fourteen-day", "14-day", "four members", "four-member", "fourteen day")
UNCONFIRMED = ("unconfirmed", "not confirmed", "neither is confirmed", "cannot confirm")

failures: list[str] = []
checked_paths = 0
skipped_tokens = 0


def clean(token: str) -> str | None:
    token = token.strip().rstrip(TRAILING)
    if not token.startswith(PATH_ROOTS):
        return None
    if any(marker in token for marker in SKIP_MARKERS):
        return None
    # `path:42` -> `path`
    token = re.sub(r":\d+(-\d+)?$", "", token)
    return token or None


def check_paths(path: Path) -> None:
    global checked_paths, skipped_tokens
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for raw in TICK.findall(line):
            candidate = clean(raw)
            if candidate is None:
                if raw.strip().startswith(PATH_ROOTS):
                    skipped_tokens += 1
                continue
            checked_paths += 1
            if not (ROOT / candidate).exists():
                failures.append(f"{path.relative_to(ROOT)}:{lineno}: cited path does not exist: {candidate}")


def paragraphs(path: Path):
    """Yield (first line number, joined paragraph text); prose wraps, so the fact check needs it."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start, buffer = 1, []
    for lineno, line in enumerate(lines, 1):
        if line.strip():
            if not buffer:
                start = lineno
            buffer.append(line)
        elif buffer:
            yield start, " ".join(buffer)
            buffer = []
    if buffer:
        yield start, " ".join(buffer)


def check_claims(path: Path) -> None:
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        lowered = line.lower()
        for pattern in BANNED:
            if pattern.search(line):
                if not any(tok.strip().startswith(PATH_ROOTS) for tok in TICK.findall(line)):
                    failures.append(
                        f"{path.relative_to(ROOT)}:{lineno}: claim '{pattern.pattern}' without a cited path on the line"
                    )
    for start, paragraph in paragraphs(path):
        lowered = paragraph.lower()
        for fact in GROUP_FACTS:
            if fact in lowered and not any(marker in lowered for marker in UNCONFIRMED):
                failures.append(
                    f"{path.relative_to(ROOT)}:{start}: group-owned fact '{fact}' stated without 'unconfirmed'"
                )


def check_components() -> None:
    numbered = sorted(p for p in REPORT_DIR.glob("[0-9][0-9]_*.md") if not p.name.startswith("00_"))
    numbers = [int(p.name[:2]) for p in numbered]
    if numbers != list(range(1, 27)):
        failures.append(f"docs/report: expected components 01..26, found {numbers}")
    for p in numbered:
        first = p.read_text(encoding="utf-8").splitlines()[0]
        expected = f"# {int(p.name[:2])}."
        if not first.startswith(expected):
            failures.append(f"docs/report/{p.name}: heading does not start with '{expected}' (found {first[:40]!r})")

    matrix = (ROOT / "docs" / "rubric_matrix.md").read_text(encoding="utf-8")
    sections = re.split(r"\n## ", matrix)
    def rows(prefix: str, heading: str) -> int:
        for section in sections:
            if section.startswith(heading):
                return len(re.findall(rf"^\| {prefix} \|", section, flags=re.MULTILINE))
        failures.append(f"docs/rubric_matrix.md: section '{heading}' not found")
        return 0

    counts = {
        "components": rows(r"\d+", "1. Report"),
        "rubric_a": rows(r"A\d+", "2. Rubric A"),
        "rubric_b": rows(r"B\d+", "3. Rubric B"),
        "topics": rows(r"P\d+", "4. Presentation"),
    }
    expected = {"components": 26, "rubric_a": 9, "rubric_b": 9, "topics": 15}
    for key, want in expected.items():
        if counts[key] != want:
            failures.append(f"docs/rubric_matrix.md: {key} rows = {counts[key]}, expected {want}")


def main() -> int:
    if not REPORT_DIR.is_dir():
        print(f"FAIL — {REPORT_DIR} does not exist")
        return 1

    for doc in DOCS:
        if not doc.exists():
            failures.append(f"missing document: {doc.relative_to(ROOT)}")
            continue
        check_paths(doc)
        if doc.parent == REPORT_DIR:
            check_claims(doc)

    check_components()

    print("=" * 78)
    print("REPORT / RUBRIC REFERENCE CHECK — Sprint 14")
    print("=" * 78)
    print(f"documents scanned      : {len(DOCS)}")
    print(f"paths checked          : {checked_paths}")
    print(f"path tokens skipped    : {skipped_tokens} (globs, ellipses, placeholders, prose)")
    print(f"components 01..26      : {'ok' if not any('components 01..26' in f for f in failures) else 'FAILED'}")
    print(f"rubric rows (26/9/9/15): {'ok' if not any('rows =' in f for f in failures) else 'FAILED'}")
    print()
    if failures:
        print(f"FAIL — {len(failures)} problem(s):")
        for failure in failures:
            print(f"  - {failure}")
        print()
        print("RESULT: FAIL")
        return 1
    print("No cited path is missing, no unsupported PASS/completed claim, no unconfirmed group fact")
    print("stated as fact, and every mandatory component has a numbered draft.")
    print()
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
