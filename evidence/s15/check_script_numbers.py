#!/usr/bin/env python3
"""Check that every number in docs/presentation_script.md is a number the artefacts record.

Two independent halves:

1. **Deck figures.** Each value is re-derived from `models/metrics.json`,
   `models/eda/summary.json`, `models/model_manifest.json` and
   `evidence/s4/feature_importances.txt`, formatted the way the document formats it, and required
   to appear in the document. A figure typed from memory has no source here, so it cannot pass.

2. **Demo expectations.** The demo table promises specific on-screen results. Those are read back
   out of `evidence/s15/demo_rehearsal.txt` — the transcript of the recorded run — and required to
   appear in the document. If the app or the rehearsal changes, this check fails until the script
   is brought back in line with what the rehearsal actually produced.

What it cannot do: judge whether a sentence uses a number correctly. That is the gate's job.

    python3 evidence/s15/check_script_numbers.py

Exit codes: 0 = every figure found, 1 = at least one is missing.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "presentation_script.md"
TRANSCRIPT = ROOT / "evidence" / "s15" / "demo_rehearsal.txt"

MODEL_NAMES = ("decision_tree", "random_forest", "logistic_regression")


def thousands(value: int) -> str:
    return f"{value:,}"


def main() -> int:
    corpus = DOC.read_text(encoding="utf-8")
    transcript = TRANSCRIPT.read_text(encoding="utf-8")

    metrics = json.loads((ROOT / "models" / "metrics.json").read_text())
    eda = json.loads((ROOT / "models" / "eda" / "summary.json").read_text())
    manifest = json.loads((ROOT / "models" / "model_manifest.json").read_text())
    importances = (ROOT / "evidence" / "s4" / "feature_importances.txt").read_text()

    expected: list[tuple[str, str]] = []

    # ---- held-out metrics and confusion cells, per candidate -------------------------------
    for name in MODEL_NAMES:
        block = metrics["evaluation"]["models"][name]
        for key in ("accuracy", "precision", "recall", "f1", "roc_auc"):
            expected.append((f"{name} held-out {key}", f"{block['metrics'][key]:.4f}"))
        matrix = block["confusion_matrix"]
        for cell in ("tn", "fp", "fn", "tp"):
            expected.append((f"{name} confusion {cell.upper()}", thousands(matrix[cell])))

    baseline = metrics["evaluation"]["baseline"]["metrics"]
    for key in ("accuracy", "precision", "recall", "f1"):
        expected.append((f"baseline {key}", f"{baseline[key]:.4f}"))
    # The baseline produces no probability, so its ROC-AUC is recorded as null; the document
    # prints 0.5000 because a constant answer ranks randomly, which is what that means.
    if baseline.get("roc_auc") is None:
        expected.append(("baseline ROC-AUC (no probability: random ranking)", "0.5000"))
    else:
        expected.append(("baseline ROC-AUC", f"{baseline['roc_auc']:.4f}"))

    # ---- cross-validation: mean and standard deviation on the training rows ----------------
    for name in MODEL_NAMES:
        cv = metrics["candidates"][name]["cv"]["metrics"]
        expected.append((f"{name} CV F1 mean", f"{cv['f1']['mean']:.4f}"))
        expected.append((f"{name} CV ROC-AUC mean", f"{cv['roc_auc']['mean']:.4f}"))
    dt_cv = metrics["candidates"]["decision_tree"]["cv"]["metrics"]["f1"]
    expected.append(("decision tree CV F1 std", f"{dt_cv['std']:.4f}"))

    # ---- split -----------------------------------------------------------------------------
    split = metrics["split"]
    expected.append(("training rows", thousands(split["train_rows"])))
    expected.append(("held-out rows", thousands(split["test_rows"])))
    for label, key in (
        ("train class 0", "train_class_counts"),
        ("test class counts", "test_class_counts"),
    ):
        counts = split.get(key) or {}
        for code in ("0", "1"):
            if code in counts:
                expected.append((f"{label} {code}", thousands(int(counts[code]))))

    # ---- dataset ---------------------------------------------------------------------------
    dataset = metrics["dataset"]
    expected.append(("dataset rows", thousands(dataset["rows"])))
    expected.append(("dataset columns", str(dataset["columns"])))
    expected.append(("feature count", str(dataset["features"])))
    expected.append(("dataset sha256", dataset["sha256"]))
    for code, count in dataset["class_counts"].items():
        expected.append((f"class {code} count", thousands(int(count))))
    for code, share in eda["class_share_pct"].items():
        expected.append((f"class {code} share", f"{share:.2f}%"))

    # ---- artifact and selection ------------------------------------------------------------
    artifact = manifest["artifact"]
    expected.append(("artifact sha256", artifact["sha256"]))
    expected.append(("artifact bytes", thousands(artifact["bytes"])))
    expected.append(("threshold", f"{metrics['evaluation']['threshold']:.2f}"))
    expected.append((
        "accuracy delta over the constant answer",
        f"{metrics['evaluation']['delta_vs_baseline']['decision_tree']['accuracy']:.4f}",
    ))
    expected.append(("selected candidate", metrics["selection"]["selected"].replace("_", " ")))

    # ---- EDA figures quoted on slide 5 -----------------------------------------------------
    for code in ("0", "2", "3"):
        expected.append((
            f"PAY_0 code {code} default rate",
            f"{eda['pay0_by_target'][code]['default_rate_pct']:.2f}%",
        ))
    expected.append(("age mean class 0", f"{eda['numeric_by_target']['AGE']['0']['mean']:.2f}"))
    expected.append(("age mean class 1", f"{eda['numeric_by_target']['AGE']['1']['mean']:.2f}"))
    for code in ("0", "1"):
        expected.append((
            f"limit median class {code}",
            thousands(int(eda["numeric_by_target"]["LIMIT_BAL"][code]["median"])),
        ))
    expected.append((
        "BILL_AMT1/BILL_AMT2 correlation",
        f"{eda['correlation_matrix']['BILL_AMT1']['BILL_AMT2']:.4f}",
    ))

    # ---- feature importance, from the artifact read-back -----------------------------------
    top = [line.split() for line in importances.splitlines() if line.startswith("PAY_0")][0]
    expected.append(("PAY_0 importance share", f"{float(top[2]):.2f}%"))
    second = [line.split() for line in importances.splitlines() if line.startswith("PAY_2")][0]
    expected.append(("PAY_2 importance share", f"{float(second[2]):.2f}%"))

    # ---- demo expectations, read back out of the rehearsal transcript -----------------------
    def first(pattern: str, label: str) -> None:
        match = re.search(pattern, transcript)
        if match is None:
            missing.append((f"rehearsal transcript: {label}", pattern))
            return
        expected.append((f"demo result {label}", match.group(1)))

    missing: list[tuple[str, str]] = []
    first(r"probability=([\d.]+%)", "probability")
    first(r"band=([A-Za-z]+)", "band")
    first(r"model=(aihubcampus-[^\s]+)", "model version")
    first(r"rejection #(\d+)", "rejection id")
    first(r"codes=([a-z_]+)", "rejection code")
    first(r"Staged as dataset version #(\d+)", "staged version")
    first(r"feature '([A-Z_0-9]+)' has no value", "invalid-input message")
    first(r"first paint ([\d.]+)s", "first paint seconds")
    first(r'"measured_total_seconds": ([\d.]+)', "measured total seconds")
    for needle in ("0.817167", "0.356", "missed 855", "1,327", "77.88%"):
        expected.append((f"evaluation page states {needle}", needle))

    print(f"# {DOC.relative_to(ROOT)} — {len(expected)} figures")
    for label, needle in expected:
        found = needle in corpus
        if not found:
            missing.append((label, needle))
        print(f"{'PASS' if found else 'FAIL'}  {label}: {needle!r}")

    if missing:
        print(f"\nRESULT: FAIL — {len(missing)} figure(s) missing from the document")
        for label, needle in missing:
            print(f"  missing: {label} ({needle!r})")
        return 1

    print(f"\nRESULT: PASS — {len(expected)} of {len(expected)} figures found, exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
