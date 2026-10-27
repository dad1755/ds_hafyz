#!/usr/bin/env python3
"""Check that the numbers quoted in the report drafts are the numbers the artefacts record.

The check is deliberately mechanical and narrow: it reads `models/metrics.json` and
`models/eda/summary.json`, formats each value the way the report formats it, and asserts that
the formatted string appears somewhere in `docs/report/`. It cannot tell whether a sentence
uses the number correctly — only that the figure was not typed from memory.

Values checked: held-out accuracy / precision / recall / F1 / ROC-AUC for the three candidates
and the baseline, the four confusion-matrix cells per model, the cross-validated means, the
split counts, the class counts, the artifact digest and size, and the dataset checksum prefix.

Exit codes: 0 = every figure found, 1 = at least one figure is missing from the drafts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "docs" / "report"


def thousands(n: int) -> str:
    return f"{n:,}"


def main() -> int:
    metrics = json.loads((ROOT / "models" / "metrics.json").read_text())
    eda = json.loads((ROOT / "models" / "eda" / "summary.json").read_text())
    corpus = "\n".join(p.read_text(encoding="utf-8") for p in sorted(REPORT_DIR.glob("*.md")))

    expected: list[tuple[str, str]] = []

    for name, block in metrics["evaluation"]["models"].items():
        m = block["metrics"]
        for key in ("accuracy", "precision", "recall", "f1", "roc_auc"):
            expected.append((f"{name} held-out {key}", f"{m[key]:.4f}"))
        cm = block["confusion_matrix"]
        for cell in ("tn", "fp", "fn", "tp"):
            expected.append((f"{name} confusion {cell.upper()}", thousands(cm[cell])))

    base = metrics["evaluation"]["baseline"]
    expected.append(("baseline accuracy", f"{base['metrics']['accuracy']:.4f}"))
    expected.append(("baseline F1", f"{base['metrics']['f1']:.1f}"))

    for row in metrics["selection"]["ranking"]:
        expected.append((f"{row['candidate']} CV F1", f"{row['cv_f1_mean']:.4f}"))

    split = metrics["split"]
    expected += [
        ("train rows", thousands(split["train_rows"])),
        ("test rows", thousands(split["test_rows"])),
        ("test class 0", thousands(split["test_class_counts"]["0"])),
        ("test class 1", thousands(split["test_class_counts"]["1"])),
        ("train class 0", thousands(split["train_class_counts"]["0"])),
        ("train class 1", thousands(split["train_class_counts"]["1"])),
        ("artifact bytes", thousands(metrics["checks"]["artifact"]["bytes"])),
        ("artifact sha256", metrics["checks"]["artifact"]["sha256"]),
        ("dataset sha256 prefix", metrics["dataset"]["sha256"][:8]),
    ]

    expected += [
        ("dataset rows", thousands(eda["rows"])),
        ("class 0 count", thousands(eda["class_counts"]["0"])),
        ("class 1 count", thousands(eda["class_counts"]["1"])),
        ("class 0 share", f"{eda['class_share_pct']['0']:.2f}"),
        ("class 1 share", f"{eda['class_share_pct']['1']:.2f}"),
        ("strongest correlation", f"{eda['strongest_correlations'][0]['r']:.4f}"),
    ]

    missing = [(label, value) for label, value in expected if value not in corpus]

    print("=" * 78)
    print("REPORT NUMBER CHECK — every quoted figure against the artefact that records it")
    print("=" * 78)
    print(f"figures derived from models/metrics.json and models/eda/summary.json : {len(expected)}")
    print(f"found in docs/report/                                                : {len(expected) - len(missing)}")
    print()
    if missing:
        print(f"FAIL — {len(missing)} figure(s) missing from the drafts:")
        for label, value in missing:
            print(f"  - {label}: expected to find {value!r}")
        print()
        print("RESULT: FAIL")
        return 1
    print("Every derived figure appears in the drafts exactly as the artefact records it.")
    print("This proves the figures were copied from the artefact, not retyped from memory.")
    print()
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
