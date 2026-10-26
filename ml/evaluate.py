#!/usr/bin/env python3
"""S4: score the three fitted pipelines once on the untouched held-out 20%.

Reads what `ml/train.py` produced (`models/metrics.json`, `models/candidates/*.joblib`),
rebuilds the identical split from the seed CSV, and scores each candidate exactly once on
the 6,000 test rows — the same rows, in the same order, that training never fitted on.

It then:

* computes accuracy, precision, recall and F1 for class 1, ROC-AUC, and the confusion
  matrix TN/FP/FN/TP for every candidate, plus the always-class-0 baseline;
* re-derives accuracy/precision/recall/F1 from each confusion matrix and asserts the two
  agree (contract §6 check 3), and asserts every matrix totals 6,000;
* draws the three confusion-matrix figures and, when a tree is selected, its feature
  importances;
* copies the selected pipeline to `models/best_pipeline.joblib`, records its checksum, and
  asserts the saved artifact reproduces the candidate's own test predictions;
* writes the evaluation section into `models/metrics.json` and writes
  `models/model_manifest.json`.

The threshold is the evaluated 0.5 (contract §4). Nothing here tunes anything.

Usage:
    python -m ml.evaluate --models-dir models
    python3 ml/evaluate.py --models-dir models
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import matplotlib

matplotlib.use("Agg")  # headless: write files, never open a window

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

try:  # `python -m ml.evaluate` from the repository root
    from ml.generate_eda import CLASS_COLORS, DPI, INK, MUTED, apply_style
    from ml.schema import FEATURES, TARGET_COLUMN
    from ml.train import CANDIDATES, SEED, TEST_SIZE, load_frame, make_split, r6
except ModuleNotFoundError:  # `python3 ml/evaluate.py` from the repository root
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ml.generate_eda import CLASS_COLORS, DPI, INK, MUTED, apply_style
    from ml.schema import FEATURES, TARGET_COLUMN
    from ml.train import CANDIDATES, SEED, TEST_SIZE, load_frame, make_split, r6

THRESHOLD = 0.5
POSITIVE_CLASS = 1
BASELINE_KEY = "always_class_0"
FIGSIZE = (3.75, 3.05)

SOURCE_LINE = (
    "Source: models/metrics.json — {n:,} held-out test rows, "
    "stratified 80/20, random_state=42"
)

CANDIDATE_KEYS = {candidate.key: candidate for candidate in CANDIDATES}


# --------------------------------------------------------------------------- helpers
def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_figure(fig: plt.Figure, out: Path, source: str) -> Path:
    """Write a PNG with a source line and reproducible metadata (no timestamp, no path)."""
    fig.text(0.008, 0.008, source, fontsize=5.6, color=MUTED, ha="left")
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, format="png", dpi=DPI, metadata={"Software": "aihubcampus ml/evaluate.py"})
    plt.close(fig)
    return out


def from_matrix(tn: int, fp: int, fn: int, tp: int) -> dict[str, float]:
    """Accuracy/precision/recall/F1 derived from the counts alone (contract §6 check 3)."""
    total = tn + fp + fn + tp
    accuracy = (tn + tp) / total
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "accuracy": r6(accuracy),
        "precision": r6(precision),
        "recall": r6(recall),
        "f1": r6(f1),
    }


def score_model(pipeline: Any, X_test: pd.DataFrame, y_test: pd.Series) -> dict[str, Any]:
    """One evaluation of one pipeline on the held-out rows."""
    probabilities = pipeline.predict_proba(X_test)[:, 1]
    predicted = (probabilities >= THRESHOLD).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, predicted, labels=[0, 1]).ravel()

    observed = {
        "accuracy": r6(accuracy_score(y_test, predicted)),
        "precision": r6(precision_score(y_test, predicted, pos_label=POSITIVE_CLASS, zero_division=0)),
        "recall": r6(recall_score(y_test, predicted, pos_label=POSITIVE_CLASS, zero_division=0)),
        "f1": r6(f1_score(y_test, predicted, pos_label=POSITIVE_CLASS, zero_division=0)),
        "roc_auc": r6(roc_auc_score(y_test, probabilities)),
    }
    derived = from_matrix(int(tn), int(fp), int(fn), int(tp))
    deltas = {name: abs(observed[name] - derived[name]) for name in derived}
    consistent = all(delta <= 1e-6 for delta in deltas.values())
    if not consistent:
        raise SystemExit(f"ERROR: metrics disagree with the confusion matrix: {deltas}")
    total = int(tn) + int(fp) + int(fn) + int(tp)
    if total != len(y_test):
        raise SystemExit(f"ERROR: confusion matrix totals {total}, expected {len(y_test)}")

    return {
        "threshold": THRESHOLD,
        "metrics": observed,
        "confusion_matrix": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp),
            "total": total,
            "labels": ["0 = no default next month", "1 = default next month"],
        },
        "arithmetic_check": {
            "derived_from_matrix": derived,
            "max_abs_delta": r6(max(deltas.values())),
            "tolerance": 1e-6,
            "verdict": "metrics consistent with TN/FP/FN/TP",
        },
    }


def baseline(y_test: pd.Series) -> dict[str, Any]:
    """Always answer class 0 — the number every model must be compared against."""
    tn = int((y_test == 0).sum())
    fn = int((y_test == 1).sum())
    counts = {"tn": tn, "fp": 0, "fn": fn, "tp": 0, "total": tn + fn}
    return {
        "description": "always predict class 0 (no default next month)",
        "threshold": "not applicable — no probability is produced",
        "metrics": {
            "accuracy": r6(tn / (tn + fn)),
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "roc_auc": None,
        },
        "confusion_matrix": counts,
        "note": (
            "Accuracy alone is not evidence of learning: a constant answer reaches "
            f"{tn / (tn + fn):.2%} on this split, which is exactly the class-0 share."
        ),
    }


def plot_confusion(matrix: dict[str, Any], title: str, out: Path) -> Path:
    """2×2 confusion matrix with labelled axes and the printed counts."""
    tn, fp = matrix["tn"], matrix["fp"]
    fn, tp = matrix["fn"], matrix["tp"]
    counts = np.array([[tn, fp], [fn, tp]], dtype=float)

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    ax.imshow(counts, cmap="Blues", vmin=0, vmax=counts.max())
    for row in range(2):
        for column in range(2):
            value = int(counts[row, column])
            share = value / counts.sum()
            dark = counts[row, column] > 0.55 * counts.max()
            ax.text(
                column,
                row,
                f"{value:,}\n({share:.1%})",
                ha="center",
                va="center",
                fontsize=8.5,
                color="white" if dark else INK,
                fontweight="bold",
            )
    labels = ["No default (0)", "Default (1)"]
    ax.set_xticks([0, 1])
    ax.set_yticks([0, 1])
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_xlabel("Predicted label", labelpad=2)
    ax.set_ylabel("Actual label", labelpad=2)
    ax.set_title(title, pad=6)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color(MUTED)
    return save_figure(fig, out, SOURCE_LINE.format(n=int(counts.sum())))


def plot_feature_importance(importances: np.ndarray, title: str, out: Path, top: int = 15) -> Path:
    """Horizontal bar chart of the selected tree's top importances."""
    order = np.argsort(importances)[::-1][:top]
    names = [FEATURES[i] for i in order]
    values = importances[order]

    fig, ax = plt.subplots(figsize=(3.75, 3.9), dpi=DPI)
    ax.barh(range(len(names)), values[::-1], color=CLASS_COLORS[0], height=0.72)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names[::-1], fontsize=6.8)
    for position, value in enumerate(values[::-1]):
        ax.text(value, position, f" {value:.3f}", va="center", fontsize=5.8, color=INK)
    ax.set_xlabel("Impurity-based importance (share of total)", labelpad=2)
    ax.set_ylabel("Feature", labelpad=2)
    ax.set_xlim(0, float(values.max()) * 1.22)
    ax.set_title(title, pad=6)
    return save_figure(fig, out, SOURCE_LINE.format(n=6000))


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score the three S4 pipelines once on the untouched held-out test set."
    )
    parser.add_argument("--models-dir", default="models", type=Path)
    parser.add_argument("--csv", default="data/UCI_Credit_Card.csv", type=Path)
    args = parser.parse_args(argv)

    models_dir: Path = args.models_dir
    metrics_path = models_dir / "metrics.json"
    if not metrics_path.is_file():
        raise SystemExit(f"ERROR: {metrics_path} not found — run `python -m ml.train` first")
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    if metrics["split"]["random_state"] != SEED or metrics["split"]["test_size"] != TEST_SIZE:
        raise SystemExit("ERROR: metrics.json records a different split than this evaluator")

    frame, dataset = load_frame(args.csv)
    split = make_split(frame)
    X_test, y_test = split["X_test"], split["y_test"]
    for side in ("train_rows", "test_rows", "train_class_counts", "test_class_counts"):
        if split["record"][side] != metrics["split"][side]:
            raise SystemExit(
                f"ERROR: rebuilt split differs from metrics.json on {side}: "
                f"{split['record'][side]} vs {metrics['split'][side]}"
            )
    if dataset["sha256"] != metrics["dataset"]["sha256"]:
        raise SystemExit("ERROR: the CSV is not the dataset the models were trained on")

    apply_style()
    figures_dir = models_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    print(f"test set : {len(X_test):,} rows, untouched until now "
          f"(class 0 {int((y_test == 0).sum()):,} / class 1 {int((y_test == 1).sum()):,})")
    print(f"threshold: {THRESHOLD}  positive class: {POSITIVE_CLASS}")
    print()

    evaluated: dict[str, dict[str, Any]] = {}
    predictions: dict[str, np.ndarray] = {}
    pipelines: dict[str, Any] = {}
    for candidate in CANDIDATES:
        artifact = models_dir / "candidates" / f"{candidate.key}.joblib"
        if not artifact.is_file():
            raise SystemExit(f"ERROR: missing candidate artifact {artifact}")
        pipeline = joblib.load(artifact)
        result = score_model(pipeline, X_test, y_test)
        result["estimator"] = candidate.estimator_name
        result["artifact"] = str(artifact)
        result["artifact_sha256"] = sha256_file(artifact)
        matrix = result["confusion_matrix"]
        figure = plot_confusion(
            matrix,
            f"{candidate.estimator_name}\n"
            f"acc {result['metrics']['accuracy']:.4f} · recall {result['metrics']['recall']:.4f} "
            f"· F1 {result['metrics']['f1']:.4f}",
            figures_dir / f"confusion_{candidate.key}.png",
        )
        result["figure"] = str(figure)
        evaluated[candidate.key] = result
        pipelines[candidate.key] = pipeline
        predictions[candidate.key] = pipeline.predict(X_test)

    base = baseline(y_test)

    selected_key = metrics["selection"]["selected"]
    if selected_key not in evaluated:
        raise SystemExit(f"ERROR: selected model {selected_key!r} has no evaluation")
    selected_candidate = CANDIDATE_KEYS[selected_key]

    # The shipped artifact: copy the selected candidate, then prove the copy still scores
    # the same rows identically (contract §6 check 2 and the §3.4 "same object" rule).
    best_path = models_dir / "best_pipeline.joblib"
    shutil.copyfile(models_dir / "candidates" / f"{selected_key}.joblib", best_path)
    best = joblib.load(best_path)
    if not np.array_equal(best.predict(X_test), predictions[selected_key]):
        raise SystemExit("ERROR: the copied best_pipeline.joblib does not reproduce the candidate")
    if not np.allclose(best.predict_proba(X_test), pipelines[selected_key].predict_proba(X_test)):
        raise SystemExit("ERROR: the copied pipeline's probabilities differ from the candidate")

    figure_paths = [evaluated[key]["figure"] for key in evaluated]
    importance_figure = None
    model_step = best.named_steps["model"]
    if hasattr(model_step, "feature_importances_"):
        importance_figure = plot_feature_importance(
            np.asarray(model_step.feature_importances_, dtype=float),
            f"{selected_candidate.estimator_name} importances\n(selected model, top 15 of 23)",
            figures_dir / "feature_importance_selected.png",
        )
        figure_paths.append(str(importance_figure))

    deltas = {
        key: {
            "accuracy": r6(payload["metrics"]["accuracy"] - base["metrics"]["accuracy"]),
            "recall": r6(payload["metrics"]["recall"] - base["metrics"]["recall"]),
            "f1": r6(payload["metrics"]["f1"] - base["metrics"]["f1"]),
        }
        for key, payload in evaluated.items()
    }

    metrics["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    metrics["evaluation"] = {
        "threshold": THRESHOLD,
        "positive_class": POSITIVE_CLASS,
        "test_rows": int(len(y_test)),
        "scored_once": True,
        "baseline": base,
        "models": evaluated,
        "selected": selected_key,
        "delta_vs_baseline": deltas,
        "figures": figure_paths,
    }
    metrics["checks"]["artifact"] = {
        "path": str(best_path),
        "sha256": sha256_file(best_path),
        "bytes": best_path.stat().st_size,
        "source_candidate": selected_key,
        "source_candidate_sha256": evaluated[selected_key]["artifact_sha256"],
        "predictions_identical_to_candidate": True,
        "probabilities_identical_to_candidate": True,
        "verdict": "the shipped pipeline reproduces its candidate's test predictions",
    }
    metrics["checks"]["arithmetic"] = {
        key: payload["arithmetic_check"]["verdict"] for key, payload in evaluated.items()
    }
    metrics["checks"]["order"] = {
        "manifest_features": list(FEATURES),
        "scores_23_column_frame": True,
        "verdict": "the shipped pipeline scores a 23-column frame in ml.schema.FEATURES order",
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "sprint": "S4",
        "created_at": metrics["generated_at"],
        "artifact": {
            "path": str(best_path),
            "sha256": metrics["checks"]["artifact"]["sha256"],
            "bytes": best_path.stat().st_size,
            "format": "joblib (scikit-learn Pipeline: transform + model)",
            "creation_path": "ml/train.py → ml/evaluate.py; never loaded from an upload",
        },
        "model": {
            "selected": selected_key,
            "estimator": selected_candidate.estimator_name,
            "hyperparameters": selected_candidate.hyperparameters,
            "transform": selected_candidate.transform,
            "threshold": THRESHOLD,
            "threshold_note": (
                "fixed at the evaluated value; an alternative threshold needs train/validation-only "
                "selection and its own evaluation evidence"
            ),
            "positive_class": POSITIVE_CLASS,
            "selection": {
                "objective": metrics["selection"]["objective"],
                "decided_by": metrics["selection"]["decided_by"],
                "test_rows_used_for_selection": 0,
            },
        },
        "features": {
            "order": list(FEATURES),
            "count": len(FEATURES),
            "dropped": ["ID", TARGET_COLUMN],
            "unit_source": "ml/schema.py COLUMN_SPECS",
        },
        "classes": {
            "0": "predicted non-default next month (not a guarantee of payment)",
            "1": "predicted default next month (not a confirmed delinquency)",
        },
        "probability_label": "Estimated model probability of next-month default",
        "calibration": "uncalibrated — no calibration test has been run",
        "dataset": {"path": dataset["path"], "sha256": dataset["sha256"]},
        "split": metrics["split"],
        "environment": metrics["environment"],
    }
    manifest_path = models_dir / "model_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"{'model':<22}{'acc':>8}{'prec':>8}{'rec':>8}{'f1':>8}{'auc':>8}   {'TN':>6}{'FP':>6}{'FN':>6}{'TP':>6}")
    for key, payload in evaluated.items():
        m = payload["metrics"]
        c = payload["confusion_matrix"]
        print(
            f"{key:<22}{m['accuracy']:>8.4f}{m['precision']:>8.4f}{m['recall']:>8.4f}"
            f"{m['f1']:>8.4f}{m['roc_auc']:>8.4f}   "
            f"{c['tn']:>6,}{c['fp']:>6,}{c['fn']:>6,}{c['tp']:>6,}"
        )
    b = base["metrics"]
    print(
        f"{BASELINE_KEY:<22}{b['accuracy']:>8.4f}{b['precision']:>8.4f}{b['recall']:>8.4f}"
        f"{b['f1']:>8.4f}{'—':>8}   {base['confusion_matrix']['tn']:>6,}"
        f"{base['confusion_matrix']['fp']:>6,}{base['confusion_matrix']['fn']:>6,}"
        f"{base['confusion_matrix']['tp']:>6,}"
    )
    print()
    print(f"selected : {selected_key}  ({selected_candidate.estimator_name})")
    print(f"shipped  : {best_path}  sha256 {metrics['checks']['artifact']['sha256']}")
    print(f"figures  : {len(figure_paths)} written to {figures_dir}/")
    for path in figure_paths:
        print(f"  {Path(path).name}")
    print(f"wrote    : {metrics_path}  and {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
