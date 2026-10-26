"""The evaluation record, read-only (blueprint §5 required artifacts; §9 SPRINT 10).

Every number the administrator's **Model evaluation** page shows is read from a generated
artifact. This module is the only place those artifacts are opened, so the page itself holds
no statistics at all:

* ``models/metrics.json`` — the S4 evaluation record written by ``ml/evaluate.py``: the three
  candidates' 5-fold cross-validation results, their held-out test metrics, the three
  confusion matrices, the constant-answer baseline, the split, the dataset checksum, the
  recorded package versions and the selection rule.
* ``models/eda/summary.json`` — the S3 aggregate record written by ``ml/generate_eda.py``: the
  class counts, per-class descriptive statistics, default rates by ``PAY_0`` and ``EDUCATION``
  code and the financial-column correlation matrix. It is what the six EDA figures were drawn
  from, and it is what their captions quote.
* ``models/best_pipeline.joblib`` — the shipped tree. Its 23 ``feature_importances_`` are read
  back from the artifact *after* :func:`ml.verify_artifact.load_verified_pipeline` has checked
  the artifact against the manifest and ``metrics.json``, because ``metrics.json`` records the
  importance *figure's path* but not the 23 values. When the selected model exposes no
  ``feature_importances_`` the function returns an empty tuple and the page says so instead of
  drawing a chart that would not mean anything.

A value that is not in one of those three artifacts is not on the page: there is no literal
metric, no date and no version string in this module or in the page it feeds. The only
constants here are file names and column labels.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"

METRICS_NAME = "metrics.json"
MANIFEST_NAME = "model_manifest.json"
ARTIFACT_NAME = "best_pipeline.joblib"
EDA_DIRNAME = "eda"
FIGURES_DIRNAME = "figures"
EDA_SUMMARY_NAME = "summary.json"

#: The six EDA figures, in the order the report presents them (blueprint §9 SPRINT 3).
EDA_FIGURE_ORDER: tuple[str, ...] = (
    "01_target_class_distribution.png",
    "02_age_by_class.png",
    "03_limit_bal_by_class.png",
    "04_default_rate_by_pay0.png",
    "05_default_rate_by_education.png",
    "06_correlation_heatmap.png",
)

#: The figures ``ml/evaluate.py`` writes beside the confusion matrices.
EVALUATION_FIGURE_ORDER: tuple[str, ...] = (
    "confusion_logistic_regression.png",
    "confusion_decision_tree.png",
    "confusion_random_forest.png",
    "feature_importance_selected.png",
)

#: Display names for the three candidates, used as table labels only.
MODEL_LABELS = {
    "logistic_regression": "Logistic Regression",
    "decision_tree": "Decision Tree",
    "random_forest": "Random Forest",
}

CLASS_LABELS = {"0": "0 = no default next month", "1": "1 = default next month"}


class EvaluationError(RuntimeError):
    """A generated artifact is missing or unreadable. The message names the file only."""


@dataclass(frozen=True)
class MetricsRecord:
    """``models/metrics.json`` plus the facts needed to cite it."""

    data: Mapping[str, Any]
    path: Path
    sha256: str

    @property
    def generated_at(self) -> str:
        return str(self.data.get("generated_at") or "")


def _models_dir(models_dir: Path | str | None) -> Path:
    return Path(models_dir) if models_dir is not None else DEFAULT_MODELS_DIR


def sha256_of(path: Path) -> str:
    """The SHA-256 of a file, read in chunks so a large artifact never lands in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise EvaluationError(
            f"{label} is not present at {path}. The image was built without it, or the "
            "artifacts have not been generated on this host."
        ) from None
    except OSError as error:
        raise EvaluationError(f"{label} at {path} could not be read: {error}") from None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        raise EvaluationError(f"{label} at {path} is not valid JSON: {error}") from None
    if not isinstance(data, dict):
        raise EvaluationError(f"{label} at {path} is not a JSON object")
    return data


def load_metrics(models_dir: Path | str | None = None) -> MetricsRecord:
    """Read the evaluation record and the digest that identifies it."""
    path = _models_dir(models_dir) / METRICS_NAME
    data = _read_json(path, METRICS_NAME)
    for key in ("candidates", "evaluation", "selection", "dataset", "split", "environment"):
        if key not in data:
            raise EvaluationError(
                f"{METRICS_NAME} at {path} has no {key!r} block; it is not an evaluation record"
            )
    return MetricsRecord(data=data, path=path, sha256=sha256_of(path))


def load_manifest(models_dir: Path | str | None = None) -> dict[str, Any]:
    """Read the model manifest the artifact was verified against."""
    return _read_json(_models_dir(models_dir) / MANIFEST_NAME, MANIFEST_NAME)


def load_eda_summary(models_dir: Path | str | None = None) -> dict[str, Any]:
    """Read the aggregate record behind the six EDA figures."""
    path = _models_dir(models_dir) / EDA_DIRNAME / EDA_SUMMARY_NAME
    data = _read_json(path, f"{EDA_DIRNAME}/{EDA_SUMMARY_NAME}")
    for key in ("class_counts", "numeric_by_target", "pay0_by_target", "correlation_matrix"):
        if key not in data:
            raise EvaluationError(
                f"{EDA_DIRNAME}/{EDA_SUMMARY_NAME} at {path} has no {key!r} block; it is not "
                "an EDA summary"
            )
    return data


def artifact_digest(models_dir: Path | str | None = None) -> str | None:
    """The SHA-256 of the artifact on disk now, or ``None`` when it is absent."""
    path = _models_dir(models_dir) / ARTIFACT_NAME
    return sha256_of(path) if path.is_file() else None


# ------------------------------------------------------------------ comparison
def _threshold_text(value: Any) -> str:
    """One column, one type: a number is shown as a fixed-precision string.

    The constant-answer baseline records its threshold as a sentence rather than a number (it
    produces no probability), and a column that mixes floats with prose makes the browser fall
    back from Arrow to JSON. Formatting here keeps the column text and keeps the display
    faithful: the digits are still the record's own value, not a statistic of this module's.
    """
    if isinstance(value, bool) or value is None:
        return "—"
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    return str(value)


def comparison_rows(metrics: Mapping[str, Any]) -> list[dict[str, Any]]:
    """One row per candidate plus the constant-answer baseline.

    Cross-validation numbers come from ``candidates.<name>.cv.metrics``; held-out test numbers
    from ``evaluation.models.<name>.metrics``; the rank from ``selection.ranking``.
    """
    evaluation = metrics["evaluation"]
    candidates = metrics["candidates"]
    ranks = {
        str(item.get("candidate")): item.get("rank")
        for item in metrics["selection"].get("ranking") or []
    }
    rows: list[dict[str, Any]] = []
    for name in sorted(candidates):
        candidate = candidates[name]
        cv = (candidate.get("cv") or {}).get("metrics") or {}
        test = ((evaluation.get("models") or {}).get(name) or {}).get("metrics") or {}
        rows.append(
            {
                "model": MODEL_LABELS.get(name, name),
                "selected": name == evaluation.get("selected"),
                "rank (CV F1)": ranks.get(name),
                "estimator": candidate.get("estimator"),
                "threshold": _threshold_text(
                    ((evaluation.get("models") or {}).get(name) or {}).get("threshold")
                ),
                "CV F1 mean": (cv.get("f1") or {}).get("mean"),
                "CV F1 std": (cv.get("f1") or {}).get("std"),
                "CV precision mean": (cv.get("precision") or {}).get("mean"),
                "CV recall mean": (cv.get("recall") or {}).get("mean"),
                "test accuracy": test.get("accuracy"),
                "test precision": test.get("precision"),
                "test recall": test.get("recall"),
                "test F1": test.get("f1"),
                "test ROC-AUC": test.get("roc_auc"),
            }
        )
    baseline = evaluation.get("baseline") or {}
    baseline_metrics = baseline.get("metrics") or {}
    rows.append(
        {
            "model": "Baseline — " + str(baseline.get("description") or "constant answer"),
            "selected": False,
            "rank (CV F1)": None,
            "estimator": "constant predictor",
            "threshold": _threshold_text(baseline.get("threshold")),
            "CV F1 mean": None,
            "CV F1 std": None,
            "CV precision mean": None,
            "CV recall mean": None,
            "test accuracy": baseline_metrics.get("accuracy"),
            "test precision": baseline_metrics.get("precision"),
            "test recall": baseline_metrics.get("recall"),
            "test F1": baseline_metrics.get("f1"),
            "test ROC-AUC": baseline_metrics.get("roc_auc"),
        }
    )
    return rows


def selection_statements(metrics: Mapping[str, Any]) -> list[str]:
    """The recorded selection objective and rule, verbatim from ``metrics.json``."""
    selection = metrics["selection"]
    lines = [f"Decided by: {selection.get('decided_by')}"]
    objective = selection.get("objective")
    if objective:
        lines.append(str(objective))
    for rule in selection.get("rule") or []:
        lines.append(f"• {rule}")
    return lines


def delta_rows(metrics: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Each candidate's improvement over the constant-answer baseline, as recorded."""
    deltas = (metrics["evaluation"].get("delta_vs_baseline") or {})
    return [
        {"model": MODEL_LABELS.get(name, name), **{f"Δ {k}": v for k, v in sorted(values.items())}}
        for name, values in sorted(deltas.items())
    ]


# ------------------------------------------------------------------ confusion matrices
def confusion_rows(metrics: Mapping[str, Any]) -> list[dict[str, Any]]:
    """TN/FP/FN/TP per candidate, straight from ``evaluation.models.<name>.confusion_matrix``."""
    models = metrics["evaluation"].get("models") or {}
    rows: list[dict[str, Any]] = []
    for name in sorted(models):
        entry = models[name] or {}
        matrix = entry.get("confusion_matrix") or {}
        check = entry.get("arithmetic_check") or {}
        rows.append(
            {
                "model": MODEL_LABELS.get(name, name),
                "TN": matrix.get("tn"),
                "FP": matrix.get("fp"),
                "FN": matrix.get("fn"),
                "TP": matrix.get("tp"),
                "total": matrix.get("total"),
                "arithmetic check": check.get("verdict"),
                "max abs delta vs metrics": check.get("max_abs_delta"),
            }
        )
    return rows


def confusion_matrices(metrics: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The three matrices in a shape a chart can draw, each with its recorded labels."""
    models = metrics["evaluation"].get("models") or {}
    panels: list[dict[str, Any]] = []
    for name in sorted(models):
        entry = models[name] or {}
        matrix = entry.get("confusion_matrix") or {}
        if not all(key in matrix for key in ("tn", "fp", "fn", "tp")):
            continue
        panels.append(
            {
                "key": name,
                "label": MODEL_LABELS.get(name, name),
                "estimator": entry.get("estimator"),
                "threshold": entry.get("threshold"),
                "tn": int(matrix["tn"]),
                "fp": int(matrix["fp"]),
                "fn": int(matrix["fn"]),
                "tp": int(matrix["tp"]),
                "total": matrix.get("total"),
                "labels": list(matrix.get("labels") or []),
                "metrics": entry.get("metrics") or {},
                "figure": entry.get("figure"),
            }
        )
    return panels


# ------------------------------------------------------------------ metadata
def metadata_rows(
    metrics: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    artifact_sha_now: str | None,
    metrics_sha: str,
    metrics_path: Path,
) -> list[dict[str, Any]]:
    """The model-metadata panel: what is deployed, trained when, on what, with which versions."""
    model = manifest.get("model") or {}
    artifact = manifest.get("artifact") or {}
    dataset = manifest.get("dataset") or {}
    recorded_dataset = metrics.get("dataset") or {}
    split = metrics.get("split") or {}
    evaluation = metrics.get("evaluation") or {}
    environment = metrics.get("environment") or {}
    manifest_evaluation = manifest.get("evaluation") or {}
    checks = metrics.get("checks") or {}

    rows = [
        ("selected model", str(evaluation.get("selected"))),
        ("selected estimator", str(model.get("estimator"))),
        ("hyperparameters", json.dumps(model.get("hyperparameters") or {}, sort_keys=True)),
        ("model version", str(model.get("version"))),
        ("decision threshold", str(model.get("threshold"))),
        ("positive class", str(model.get("positive_class"))),
        ("trained / manifest written (UTC)", str(manifest.get("created_at"))),
        ("evaluation record generated (UTC)", str(metrics.get("generated_at"))),
        ("evaluation method", _evaluation_method(evaluation, split, metrics)),
        ("held-out test rows", f"{evaluation.get('test_rows'):,}" if evaluation.get("test_rows") else "—"),
        ("scored exactly once", str(evaluation.get("scored_once"))),
        ("training rows", f"{split.get('train_rows'):,}" if split.get("train_rows") else "—"),
        ("split function", str(split.get("function"))),
        ("dataset path", str(dataset.get("path"))),
        ("dataset sha256", str(dataset.get("sha256"))),
        ("dataset rows", str(recorded_dataset.get("rows"))),
        ("dataset columns / features", f"{recorded_dataset.get('columns')} / {recorded_dataset.get('features')}"),
        ("dataset class counts", json.dumps(recorded_dataset.get("class_counts") or {}, sort_keys=True)),
        ("deployed artifact", str(artifact.get("path"))),
        ("artifact sha256 (manifest)", str(artifact.get("sha256"))),
        ("artifact sha256 (on disk now)", artifact_sha_now or "absent"),
        ("artifact matches its manifest", str(bool(artifact_sha_now) and artifact.get("sha256") == artifact_sha_now)),
        ("artifact check", str((checks.get("artifact") or {}).get("verdict"))),
        (
            "package versions",
            ", ".join(f"{name} {version}" for name, version in sorted(environment.items())),
        ),
        ("manifest package versions", ", ".join(
            f"{name} {version}" for name, version in sorted((manifest.get("environment") or {}).items())
        )),
        ("calibration", str(manifest.get("calibration"))),
        ("evaluation record", f"{metrics_path} (sha256 {metrics_sha})"),
    ]
    if manifest_evaluation.get("note"):
        rows.append(("manifest evaluation note", str(manifest_evaluation["note"])))
    return [{"field": field, "value": value} for field, value in rows]


def _evaluation_method(
    evaluation: Mapping[str, Any], split: Mapping[str, Any], metrics: Mapping[str, Any]
) -> str:
    """A sentence assembled from the recorded split, evaluation and selection facts."""
    used_for_selection = (metrics.get("selection") or {}).get("test_rows_used_for_selection")
    return (
        f"single stratified hold-out: {split.get('train_rows')} training rows and "
        f"{evaluation.get('test_rows')} test rows ({split.get('function')}); each candidate "
        f"scored once on the test rows at threshold {evaluation.get('threshold')} with "
        f"positive class {evaluation.get('positive_class')}; the test rows took no part in "
        f"model selection ({used_for_selection} test rows used for selection)"
    )


# ------------------------------------------------------------------ limitations
def limitation_statements(metrics: Mapping[str, Any], manifest: Mapping[str, Any]) -> list[str]:
    """The honest limits, each number read from the record rather than written here."""
    evaluation = metrics["evaluation"]
    selected = evaluation.get("selected")
    entry = (evaluation.get("models") or {}).get(selected) or {}
    matrix = entry.get("confusion_matrix") or {}
    recorded = entry.get("metrics") or {}
    tp, fn = int(matrix.get("tp", 0)), int(matrix.get("fn", 0))
    positives = tp + fn
    recall = recorded.get("recall")
    threshold = entry.get("threshold")
    baseline = evaluation.get("baseline") or {}
    baseline_metrics = baseline.get("metrics") or {}

    statements: list[str] = []
    if positives:
        missed_share = fn / positives
        statements.append(
            f"**It misses most defaults.** On the {evaluation.get('test_rows'):,} held-out "
            f"accounts the deployed model caught {tp:,} of the {positives:,} that actually "
            f"defaulted and missed {fn:,} ({missed_share:.1%}). Recall is "
            f"{float(recall):.3f} at threshold {threshold}, so a *no default* answer is not "
            "a statement that the account will pay."
        )
    if baseline_metrics:
        statements.append(
            f"**Accuracy flatters it.** {baseline.get('note')} The deployed model's accuracy "
            f"of {float(recorded.get('accuracy')):.6f} is only "
            f"{float((evaluation.get('delta_vs_baseline') or {}).get(selected, {}).get('accuracy', 0.0)):+.6f} "
            "above that constant answer, which is why F1 and recall are reported beside it."
        )
    calibration = manifest.get("calibration")
    if calibration:
        statements.append(
            f"**The probability is not a risk percentage.** {calibration}. The number is the "
            "model's own score and has not been calibrated against real default rates."
        )
    statements.append(
        "**This is not a credit decision.** The model is an academic demonstration on 2005 "
        "Taiwanese credit-card data; it does not decide, refuse or price anything, and "
        "demographic features are a known fairness risk discussed in the report."
    )
    return statements


# ------------------------------------------------------------------ EDA panels
def _share(value: Any) -> str:
    return f"{float(value):.2f}%"


def eda_panels(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The six EDA figures with a caption built from ``summary.json``.

    Each panel carries ``file``, ``title``, ``caption`` (all numbers from the summary),
    ``alt`` (the same content as a sentence, for a screen reader) and an optional ``table``
    of the numbers that the figure encodes in colour alone.
    """
    counts = summary["class_counts"]
    share = summary.get("class_share_pct") or {}
    numeric = summary["numeric_by_target"]
    pay0 = summary["pay0_by_target"]
    education = summary["education_by_target"]
    strongest = summary.get("strongest_correlations") or []
    rows = summary.get("rows")

    zero, one = counts.get("0"), counts.get("1")
    ratio = (zero / one) if zero and one else None
    class_caption = (
        f"Class 0 (no default) = {zero:,} accounts ({_share(share.get('0'))}); class 1 "
        f"(default) = {one:,} accounts ({_share(share.get('1'))})."
    )
    if ratio:
        class_caption += (
            f" The majority class outweighs the minority {ratio:.2f} to 1, so a model that "
            f"always answers *no default* already reaches {float(share.get('0')):.2f}% "
            "accuracy — accuracy alone cannot show learning."
        )

    age = numeric.get("AGE") or {}
    limit = numeric.get("LIMIT_BAL") or {}
    age_caption = (
        f"Median age {float((age.get('0') or {}).get('median')):.0f} years for class 0 and "
        f"{float((age.get('1') or {}).get('median')):.0f} for class 1; the middle half of each "
        f"class spans {float((age.get('0') or {}).get('q25')):.0f}–{float((age.get('0') or {}).get('q75')):.0f} "
        f"and {float((age.get('1') or {}).get('q25')):.0f}–{float((age.get('1') or {}).get('q75')):.0f} "
        "years. The two distributions nearly coincide, so age on its own separates the "
        "classes poorly."
    )
    limit_caption = (
        f"Median credit limit NT${float((limit.get('0') or {}).get('median')):,.0f} for class 0 "
        f"and NT${float((limit.get('1') or {}).get('median')):,.0f} for class 1 (means "
        f"NT${float((limit.get('0') or {}).get('mean')):,.0f} and "
        f"NT${float((limit.get('1') or {}).get('mean')):,.0f}). Accounts that defaulted hold "
        "smaller limits, but the ranges overlap heavily."
    )

    def rate_caption(name: str, grouped: Mapping[str, Any], note: str) -> str:
        parts = []
        for code in sorted(grouped, key=float):
            entry = grouped[code]
            parts.append(
                f"{name}={code}: {float(entry.get('default_rate_pct')):.2f}% "
                f"(n={int(entry.get('count')):,})"
            )
        return "; ".join(parts) + f". {note}"

    pay0_caption = rate_caption(
        "PAY_0",
        pay0,
        "Repayment status is the strongest single signal in the data: the rate climbs from "
        "the *paid in full* codes to the codes reporting months of delay",
    )
    education_caption = rate_caption(
        "EDUCATION",
        education,
        "The education codes are broad and unevenly populated, so the differences are weaker "
        "and less reliable than the repayment-status pattern",
    )

    top = strongest[:5]
    correlation_caption = (
        "Pearson r between the credit limit, the six statement balances and the six payment "
        "amounts. The balances move together, which is why the model can lean on one or two "
        "of them."
    )
    if top:
        correlation_caption += " Strongest pairs: " + "; ".join(
            f"{item.get('a')}–{item.get('b')} r={float(item.get('r')):.4f}" for item in top
        ) + "."

    source_note = f"Source: UCI_Credit_Card.csv — {rows:,} accounts, Taiwan, Apr–Sep 2005." if rows else ""

    panels = [
        {
            "file": EDA_FIGURE_ORDER[0],
            "title": "Class distribution",
            "caption": class_caption,
            "alt": class_caption,
        },
        {
            "file": EDA_FIGURE_ORDER[1],
            "title": "Age by class",
            "caption": age_caption,
            "alt": age_caption,
        },
        {
            "file": EDA_FIGURE_ORDER[2],
            "title": "Credit limit by class",
            "caption": limit_caption,
            "alt": limit_caption,
        },
        {
            "file": EDA_FIGURE_ORDER[3],
            "title": "Default rate by repayment status (PAY_0)",
            "caption": pay0_caption,
            "alt": pay0_caption,
        },
        {
            "file": EDA_FIGURE_ORDER[4],
            "title": "Default rate by education code",
            "caption": education_caption,
            "alt": education_caption,
        },
        {
            "file": EDA_FIGURE_ORDER[5],
            "title": "Correlation between the financial columns",
            "caption": correlation_caption,
            "alt": correlation_caption,
            "table": [
                {
                    "column A": item.get("a"),
                    "column B": item.get("b"),
                    "Pearson r": item.get("r"),
                }
                for item in strongest
            ],
        },
    ]
    for panel in panels:
        panel["caption"] = f"{panel['caption']} {source_note}".strip()
        panel["alt"] = panel["caption"]
    return panels


# ------------------------------------------------------------------ feature importance
def feature_importances(models_dir: Path | str | None = None) -> tuple[list[dict[str, Any]], str]:
    """The deployed tree's 23 importances, read from the verified artifact.

    Returns ``(rows, note)``. ``rows`` is empty and ``note`` explains why when the selected
    model does not expose ``feature_importances_`` (a documented alternative to the chart).
    """
    from ml.verify_artifact import ArtifactError, load_verified_pipeline

    directory = _models_dir(models_dir)
    try:
        pipeline, manifest = load_verified_pipeline(directory)
    except ArtifactError as error:
        raise EvaluationError(f"the model artifact failed verification: {error}") from None
    order = list((manifest.get("features") or {}).get("order") or [])
    step = getattr(pipeline, "named_steps", {}).get("model", pipeline)
    values = getattr(step, "feature_importances_", None)
    if values is None or not order:
        return [], (
            f"the deployed {manifest.get('model', {}).get('estimator', 'model')} exposes no "
            "feature_importances_; feature importance is therefore not charted"
        )
    if len(values) != len(order):
        raise EvaluationError(
            f"the artifact reports {len(values)} importances for {len(order)} features"
        )
    total = float(sum(float(value) for value in values))
    rows = [
        {
            "feature": name,
            "importance": float(value),
            "share of total": (float(value) / total) if total else 0.0,
        }
        for name, value in zip(order, values, strict=True)
    ]
    rows.sort(key=lambda row: row["importance"], reverse=True)
    return rows, (
        f"read from the verified artifact {ARTIFACT_NAME} (sha256 "
        f"{str((manifest.get('artifact') or {}).get('sha256'))[:16]}…); impurity-based "
        "importances for the selected decision tree"
    )


# ------------------------------------------------------------------ figures on disk
def figure_paths(models_dir: Path | str | None = None) -> dict[str, Path]:
    """Every figure the page shows, keyed by file name, with the path it is read from."""
    directory = _models_dir(models_dir)
    paths: dict[str, Path] = {}
    for name in EDA_FIGURE_ORDER:
        paths[name] = directory / EDA_DIRNAME / name
    for name in EVALUATION_FIGURE_ORDER:
        paths[name] = directory / FIGURES_DIRNAME / name
    return paths


def missing_figures(models_dir: Path | str | None = None) -> list[str]:
    """Figure files that are not on disk, so the page can say which ones are absent."""
    return [name for name, path in figure_paths(models_dir).items() if not path.is_file()]


__all__: Sequence[str] = [
    "CLASS_LABELS",
    "DEFAULT_MODELS_DIR",
    "EDA_FIGURE_ORDER",
    "EVALUATION_FIGURE_ORDER",
    "EvaluationError",
    "MODEL_LABELS",
    "MetricsRecord",
    "artifact_digest",
    "comparison_rows",
    "confusion_matrices",
    "confusion_rows",
    "delta_rows",
    "eda_panels",
    "feature_importances",
    "figure_paths",
    "limitation_statements",
    "load_eda_summary",
    "load_manifest",
    "load_metrics",
    "metadata_rows",
    "missing_figures",
    "selection_statements",
    "sha256_of",
]
