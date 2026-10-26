#!/usr/bin/env python3
"""S4: fit the three candidate pipelines and select one on train-only cross-validation.

This script implements `docs/preprocessing_contract.md` exactly. It:

1. loads and validates `data/UCI_Credit_Card.csv` (SHA-256 asserted against the seed),
2. drops `ID` and the target, keeping the 23 features of `ml.schema.FEATURES` in order,
3. makes the one fixed split — `train_test_split(test_size=0.2, stratify=y,
   random_state=42)` — and records the actual per-side class counts,
4. builds one `Pipeline` per candidate, with a `ColumnTransformer` as the first step
   (`StandardScaler` for LogisticRegression, `passthrough` for both trees),
5. runs 5-fold stratified cross-validation **on the training rows only**, fits each
   pipeline on the full training set, and saves every fitted pipeline,
6. selects a model from the cross-validation numbers alone.

The held-out 6,000 rows are created here but never scored here: `ml/evaluate.py` touches
them once. Nothing in this file reads `y_test` except to count it.

Outputs (`--out`, default `models`):

* ``models/metrics.json`` — dataset identity, split, hyper-parameters, CV numbers,
  selection and package versions. `ml/evaluate.py` appends the test-set section to the
  same file, so there is one metrics document per build.
* ``models/candidates/<key>.joblib`` — each fitted pipeline (transform + estimator).

Usage:
    python -m ml.train --csv data/UCI_Credit_Card.csv --out models
    python3 ml/train.py --csv data/UCI_Credit_Card.csv --out models
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

try:  # `python -m ml.train` from the repository root
    from ml.schema import FEATURES, SEED_SHA256, SEED_METADATA_CHECKSUM, TARGET_COLUMN
    from src.validation import validate_dataframe
except ModuleNotFoundError:  # `python3 ml/train.py` from the repository root
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ml.schema import FEATURES, SEED_SHA256, SEED_METADATA_CHECKSUM, TARGET_COLUMN
    from src.validation import validate_dataframe

# --------------------------------------------------------------------------- contract

#: Everything reproducible hangs off this one seed (`docs/preprocessing_contract.md` §2).
SEED = 42
TEST_SIZE = 0.2
CV_FOLDS = 5
#: Absolute CV-F1 gap inside which two candidates count as tied and recall decides.
TIE_EPSILON = 0.005

SCORERS = {
    "f1": "f1",
    "precision": "precision",
    "recall": "recall",
    "roc_auc": "roc_auc",
}


@dataclass(frozen=True)
class Candidate:
    """One of the three fixed candidates of blueprint §5 step 4."""

    key: str
    estimator_name: str
    transform: str
    scaled: bool
    hyperparameters: dict[str, Any]
    factory: Callable[[], Any]


CANDIDATES: tuple[Candidate, ...] = (
    Candidate(
        key="logistic_regression",
        estimator_name="LogisticRegression",
        transform="StandardScaler fitted on X_train only",
        scaled=True,
        hyperparameters={"max_iter": 1000, "random_state": SEED},
        factory=lambda: LogisticRegression(max_iter=1000, random_state=SEED),
    ),
    Candidate(
        key="decision_tree",
        estimator_name="DecisionTreeClassifier",
        transform="passthrough (a tree splits on order, not distance)",
        scaled=False,
        hyperparameters={"max_depth": 5, "random_state": SEED},
        factory=lambda: DecisionTreeClassifier(max_depth=5, random_state=SEED),
    ),
    Candidate(
        key="random_forest",
        estimator_name="RandomForestClassifier",
        transform="passthrough (a tree splits on order, not distance)",
        scaled=False,
        hyperparameters={"n_estimators": 100, "max_depth": 5, "random_state": SEED},
        factory=lambda: RandomForestClassifier(n_estimators=100, max_depth=5, random_state=SEED),
    ),
)

SELECTION_OBJECTIVE = (
    "Maximise mean 5-fold cross-validated F1 on class 1 (default next month) on the "
    "training rows only. F1 is the primary objective because 77.88% of the sample is "
    "class 0, so accuracy is dominated by the majority class; F1 balances default-class "
    "recall against the false-positive cost that precision charges for. Ties within "
    f"{TIE_EPSILON} absolute CV F1 are broken by higher mean CV recall, then higher mean "
    "CV precision. A candidate whose mean CV F1 is not above zero is ineligible. The "
    "held-out test set plays no part in this choice."
)


# --------------------------------------------------------------------------- helpers
def r6(value: float) -> float:
    """Round for the JSON record; six decimals is well inside the tolerance the gate uses."""
    return round(float(value), 6)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "scikit-learn": sklearn.__version__,
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "joblib": joblib.__version__,
    }


def build_pipeline(candidate: Candidate) -> Pipeline:
    """One `Pipeline` per candidate, `ColumnTransformer` first (contract §3)."""
    inner: Any = StandardScaler() if candidate.scaled else "passthrough"
    transform = ColumnTransformer(
        transformers=[("features", inner, list(FEATURES))],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    return Pipeline([("transform", transform), ("model", candidate.factory())])


def load_frame(csv_path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read the seed CSV, assert its identity and validate it against the S2 contract."""
    if not csv_path.is_file():
        raise SystemExit(f"ERROR: CSV not found: {csv_path}")
    digest = sha256_file(csv_path)
    if digest != SEED_SHA256:
        raise SystemExit(
            f"ERROR: {csv_path} is not the immutable seed\n  expected {SEED_SHA256}\n  observed {digest}"
        )

    frame = pd.read_csv(csv_path)
    report = validate_dataframe(frame)
    if not report.ok:
        raise SystemExit(
            "ERROR: the dataset fails the S2 contract: " + "; ".join(report.messages())
        )

    counts = frame[TARGET_COLUMN].value_counts().sort_index()
    dataset = {
        "path": str(csv_path),
        "sha256": digest,
        "rows": int(len(frame)),
        "columns": int(frame.shape[1]),
        "features": len(FEATURES),
        "class_counts": {str(int(k)): int(v) for k, v in counts.items()},
        "metadata_checksum": report.metadata_checksum,
        "seed_metadata_checksum": SEED_METADATA_CHECKSUM,
    }
    return frame, dataset


def make_split(frame: pd.DataFrame) -> dict[str, Any]:
    """The one fixed split. Returns the frames plus the recorded counts."""
    X = frame.loc[:, list(FEATURES)]
    y = frame[TARGET_COLUMN].astype(int)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=SEED
    )
    train_counts = y_train.value_counts().sort_index()
    test_counts = y_test.value_counts().sort_index()
    record = {
        "function": "train_test_split(test_size=0.2, stratify=y, random_state=42)",
        "test_size": TEST_SIZE,
        "random_state": SEED,
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "train_class_counts": {str(int(k)): int(v) for k, v in train_counts.items()},
        "test_class_counts": {str(int(k)): int(v) for k, v in test_counts.items()},
        "features": list(FEATURES),
        "dropped": ["ID", TARGET_COLUMN],
        "target_column": TARGET_COLUMN,
        "positive_class": 1,
    }
    return {"X_train": X_train, "X_test": X_test, "y_train": y_train, "y_test": y_test, "record": record}


def cross_validate_candidate(candidate: Candidate, X_train: pd.DataFrame, y_train: pd.Series) -> dict[str, Any]:
    """5-fold stratified CV on the training rows only — the test rows are not an argument."""
    cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=SEED)
    scores = cross_validate(
        build_pipeline(candidate), X_train, y_train, cv=cv, scoring=SCORERS, n_jobs=1
    )
    metrics: dict[str, Any] = {}
    for name in SCORERS:
        values = [r6(v) for v in scores[f"test_{name}"]]
        metrics[name] = {
            "mean": r6(np.mean(values)),
            "std": r6(np.std(values, ddof=0)),
            "folds": values,
        }
    return {
        "folds": CV_FOLDS,
        "strategy": f"StratifiedKFold(n_splits={CV_FOLDS}, shuffle=True, random_state={SEED})",
        "rows": int(len(X_train)),
        "scored_on": "training rows only",
        "metrics": metrics,
    }


def select_model(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Apply :data:`SELECTION_OBJECTIVE` to the CV numbers."""
    ranked = sorted(
        results.items(),
        key=lambda item: (
            -item[1]["cv"]["metrics"]["f1"]["mean"],
            -item[1]["cv"]["metrics"]["recall"]["mean"],
            -item[1]["cv"]["metrics"]["precision"]["mean"],
        ),
    )
    ranking = [
        {
            "rank": position,
            "candidate": key,
            "cv_f1_mean": payload["cv"]["metrics"]["f1"]["mean"],
            "cv_recall_mean": payload["cv"]["metrics"]["recall"]["mean"],
            "cv_precision_mean": payload["cv"]["metrics"]["precision"]["mean"],
        }
        for position, (key, payload) in enumerate(ranked, start=1)
    ]

    eligible = [item for item in ranked if item[1]["cv"]["metrics"]["f1"]["mean"] > 0]
    if not eligible:
        raise SystemExit("ERROR: no candidate reached a positive cross-validated F1")
    winner_key, winner = eligible[0]
    best_f1 = winner["cv"]["metrics"]["f1"]["mean"]
    tied = [
        item
        for item in eligible
        if best_f1 - item[1]["cv"]["metrics"]["f1"]["mean"] <= TIE_EPSILON
    ]
    decided_by = "cv_f1"
    if len(tied) > 1:
        tied.sort(key=lambda item: -item[1]["cv"]["metrics"]["recall"]["mean"])
        winner_key, winner = tied[0]
        decided_by = "cv_recall (within the tie band)"

    return {
        "objective": SELECTION_OBJECTIVE,
        "rule": [
            "rank by mean 5-fold CV F1 on class 1",
            f"treat gaps <= {TIE_EPSILON} as a tie and prefer the higher mean CV recall",
            "then the higher mean CV precision",
            "cross-validation runs on the 24,000 training rows only",
            "the held-out 6,000 rows are scored once, later, by ml/evaluate.py",
        ],
        "ranking": ranking,
        "selected": winner_key,
        "decided_by": decided_by,
        "test_rows_used_for_selection": 0,
    }


def leakage_check(pipeline: Pipeline, X_train: pd.DataFrame, X_all: pd.DataFrame) -> dict[str, Any]:
    """Prove the scaler was fitted on the training rows, not on the whole dataset."""
    scaler = pipeline.named_steps["transform"].named_transformers_["features"]
    train_mean = X_train.to_numpy(dtype=float).mean(axis=0)
    full_mean = X_all.to_numpy(dtype=float).mean(axis=0)
    fitted_mean = np.asarray(scaler.mean_, dtype=float)
    train_delta = float(np.max(np.abs(fitted_mean - train_mean)))
    full_delta = float(np.max(np.abs(fitted_mean - full_mean)))
    if train_delta > 1e-6:
        raise SystemExit(
            "ERROR: the scaler's mean_ does not match X_train — the transform was not fitted on train"
        )
    index = list(FEATURES).index("LIMIT_BAL")
    return {
        "checked_on": "logistic_regression",
        "max_abs_delta_vs_train_mean": train_delta,
        "max_abs_delta_vs_full_dataset_mean": full_delta,
        "verdict": "scaler fitted on X_train only",
        "limit_bal_mean_train": r6(train_mean[index]),
        "limit_bal_mean_full": r6(full_mean[index]),
        "limit_bal_scaler_mean": r6(fitted_mean[index]),
        "tolerance": 1e-6,
    }


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fit the three S4 candidate pipelines and select one on train-only CV."
    )
    parser.add_argument("--csv", default="data/UCI_Credit_Card.csv", type=Path)
    parser.add_argument("--out", default="models", type=Path)
    args = parser.parse_args(argv)

    frame, dataset = load_frame(args.csv)
    split = make_split(frame)
    X_train, y_train = split["X_train"], split["y_train"]

    candidates_dir = args.out / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)

    print(f"dataset  : {dataset['path']}")
    print(f"sha256   : {dataset['sha256']}")
    print(f"rows     : {dataset['rows']:,}  features: {dataset['features']}  (ID and target dropped)")
    print(
        f"split    : train {split['record']['train_rows']:,} "
        f"{split['record']['train_class_counts']}  test {split['record']['test_rows']:,} "
        f"{split['record']['test_class_counts']}  (random_state={SEED}, stratified)"
    )
    print()

    results: dict[str, dict[str, Any]] = {}
    fitted: dict[str, Pipeline] = {}
    for candidate in CANDIDATES:
        print(f"fitting {candidate.key} ({candidate.estimator_name}) ...", flush=True)
        cv = cross_validate_candidate(candidate, X_train, y_train)
        pipeline = build_pipeline(candidate)
        pipeline.fit(X_train, y_train)
        artifact = candidates_dir / f"{candidate.key}.joblib"
        joblib.dump(pipeline, artifact)
        fitted[candidate.key] = pipeline
        results[candidate.key] = {
            "estimator": candidate.estimator_name,
            "hyperparameters": candidate.hyperparameters,
            "transform": candidate.transform,
            "scaled": candidate.scaled,
            "cv": cv,
            "artifact": str(artifact),
            "artifact_sha256": sha256_file(artifact),
            "artifact_bytes": artifact.stat().st_size,
        }

    selection = select_model(results)
    checks = {
        "leakage": leakage_check(
            fitted["logistic_regression"], X_train, frame.loc[:, list(FEATURES)]
        ),
        "feature_order": {
            "manifest_features": list(FEATURES),
            "count": len(FEATURES),
            "matches_schema": True,
            "verdict": "pipelines consume the 23 features in ml.schema.FEATURES order",
        },
    }

    metrics = {
        "schema_version": 1,
        "sprint": "S4",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset": dataset,
        "split": split["record"],
        "environment": package_versions(),
        "candidates": results,
        "selection": selection,
        "checks": checks,
    }
    metrics_path = args.out / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print()
    print(f"{'candidate':<22}{'cv_f1':>9}{'cv_prec':>9}{'cv_rec':>9}{'cv_auc':>9}")
    for key, payload in results.items():
        m = payload["cv"]["metrics"]
        print(
            f"{key:<22}{m['f1']['mean']:>9.4f}{m['precision']['mean']:>9.4f}"
            f"{m['recall']['mean']:>9.4f}{m['roc_auc']['mean']:>9.4f}"
        )
    print()
    print(f"selected : {selection['selected']}  (decided by {selection['decided_by']})")
    print(f"wrote    : {metrics_path}  and {len(results)} candidate pipelines in {candidates_dir}/")
    print("next     : python -m ml.evaluate --models-dir models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
