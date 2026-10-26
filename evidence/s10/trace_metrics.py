"""S10 evidence — every number the page shows, traced to the record it came from.

Run inside the built image, from the repository root:

    docker run --rm -v "$PWD:/app:z" -w /app aihubcampus-web:s10 \
        python evidence/s10/trace_metrics.py

The page itself never opens ``models/metrics.json``: it asks :mod:`src.evaluation`, which asks
the file. So this probe builds two independent renderings of the same facts —

* **A — what the page displays**: the rows returned by ``src.evaluation.comparison_rows``,
  ``confusion_matrices``, ``confusion_rows``, ``metadata_rows`` and ``eda_panels``, formatted
  exactly as Streamlit shows them;
* **B — what the file says**: the same facts read straight out of ``models/metrics.json`` and
  ``models/model_manifest.json`` with ``json`` and string formatting here, importing nothing
  from ``src``.

— and diffs A against B with ``difflib.unified_diff``. An empty diff for a section is the
claim "the page shows the record". A non-empty one prints the offending lines and the process
exits 1, so this cannot quietly pass.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

from src import charts, evaluation

MODELS = Path("models")
METRICS = json.loads((MODELS / "metrics.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((MODELS / "model_manifest.json").read_text(encoding="utf-8"))

FAILURES: list[str] = []


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _number(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def _diff(label: str, shown: list[str], recorded: list[str]) -> None:
    print(f"\n--- {label}: A = page, B = metrics.json " + "-" * (58 - len(label)))
    diff = list(
        difflib.unified_diff(recorded, shown, fromfile="B metrics.json", tofile="A page",
                             lineterm="", n=1)
    )
    if diff:
        FAILURES.append(label)
        print("\n".join(diff))
    else:
        print(f"no differences — {len(shown)} lines identical")
        print("\n".join(f"  {line}" for line in shown))


# --------------------------------------------------------------- 1. comparison table
def comparison() -> None:
    rows = {row["model"]: row for row in evaluation.comparison_rows(METRICS)}
    shown: list[str] = []
    recorded: list[str] = []
    for name in sorted(METRICS["candidates"]):
        candidate = METRICS["candidates"][name]
        entry = METRICS["evaluation"]["models"][name]
        cv = candidate["cv"]["metrics"]
        label = evaluation.MODEL_LABELS[name]
        row = rows[label]
        for column, path, value in (
            ("test accuracy", f"evaluation.models.{name}.metrics.accuracy",
             entry["metrics"]["accuracy"]),
            ("test precision", f"evaluation.models.{name}.metrics.precision",
             entry["metrics"]["precision"]),
            ("test recall", f"evaluation.models.{name}.metrics.recall",
             entry["metrics"]["recall"]),
            ("test F1", f"evaluation.models.{name}.metrics.f1", entry["metrics"]["f1"]),
            ("test ROC-AUC", f"evaluation.models.{name}.metrics.roc_auc",
             entry["metrics"]["roc_auc"]),
            ("CV F1 mean", f"candidates.{name}.cv.metrics.f1.mean", cv["f1"]["mean"]),
            ("CV F1 std", f"candidates.{name}.cv.metrics.f1.std", cv["f1"]["std"]),
            ("CV precision mean", f"candidates.{name}.cv.metrics.precision.mean",
             cv["precision"]["mean"]),
            ("CV recall mean", f"candidates.{name}.cv.metrics.recall.mean",
             cv["recall"]["mean"]),
        ):
            shown.append(f"{label:20s} | {column:18s} | {_number(row[column])}")
            recorded.append(f"{label:20s} | {column:18s} | {_number(value)}")
        shown.append(f"{label:20s} | {'threshold':18s} | {row['threshold']}")
        recorded.append(f"{label:20s} | {'threshold':18s} | {entry['threshold']:.2f}")
        shown.append(f"{label:20s} | {'estimator':18s} | {row['estimator']}")
        recorded.append(f"{label:20s} | {'estimator':18s} | {candidate['estimator']}")

    baseline = METRICS["evaluation"]["baseline"]
    label = "Baseline — " + str(baseline["description"])
    row = rows[label]
    for column, key in (("test accuracy", "accuracy"), ("test precision", "precision"),
                        ("test recall", "recall"), ("test F1", "f1"),
                        ("test ROC-AUC", "roc_auc")):
        shown.append(f"{label[:20]:20s} | {column:18s} | {_number(row[column])}")
        recorded.append(f"{label[:20]:20s} | {column:18s} | {_number(baseline['metrics'][key])}")
    shown.append(f"{label[:20]:20s} | {'threshold':18s} | {row['threshold']}")
    recorded.append(f"{label[:20]:20s} | {'threshold':18s} | {baseline['threshold']}")

    _diff("comparison table", shown, recorded)


# --------------------------------------------------------------- 2. confusion matrices
def confusion() -> None:
    panels = {panel["key"]: panel for panel in evaluation.confusion_matrices(METRICS)}
    shown: list[str] = []
    recorded: list[str] = []
    for name in sorted(METRICS["evaluation"]["models"]):
        matrix = METRICS["evaluation"]["models"][name]["confusion_matrix"]
        panel = panels[name]
        label = evaluation.MODEL_LABELS[name]
        for cell in ("tn", "fp", "fn", "tp"):
            shown.append(f"{label:20s} | {cell.upper():2s} | {panel[cell]:>6,d}")
            recorded.append(f"{label:20s} | {cell.upper():2s} | {matrix[cell]:>6,d}")
        shown.append(f"{label:20s} | total | {panel['total']:>6,d}")
        recorded.append(f"{label:20s} | total | {matrix['total']:>6,d}")
        total_shown = panel["tn"] + panel["fp"] + panel["fn"] + panel["tp"]
        if total_shown != panel["total"]:
            FAILURES.append(f"{name}: cells do not sum to the recorded total")

    _diff("confusion matrices", shown, recorded)


# --------------------------------------------------------------- 3. metadata panel
def metadata() -> None:
    record = evaluation.load_metrics(MODELS)
    rows = {
        row["field"]: row["value"]
        for row in evaluation.metadata_rows(
            record.data,
            MANIFEST,
            artifact_sha_now=evaluation.artifact_digest(MODELS),
            metrics_sha=record.sha256,
            metrics_path=record.path,
        )
    }
    artifact_sha = _sha256(MODELS / "best_pipeline.joblib")
    expected = {
        "selected model": METRICS["evaluation"]["selected"],
        "selected estimator": MANIFEST["model"]["estimator"],
        "model version": MANIFEST["model"]["version"],
        "decision threshold": str(MANIFEST["model"]["threshold"]),
        "trained / manifest written (UTC)": MANIFEST["created_at"],
        "evaluation record generated (UTC)": METRICS["generated_at"],
        "dataset sha256": MANIFEST["dataset"]["sha256"],
        "dataset rows": str(METRICS["dataset"]["rows"]),
        "deployed artifact": MANIFEST["artifact"]["path"],
        "artifact sha256 (manifest)": MANIFEST["artifact"]["sha256"],
        "artifact sha256 (on disk now)": artifact_sha,
        "artifact matches its manifest": "True",
        "evaluation record": f"models/metrics.json (sha256 {record.sha256})",
    }
    print("\n--- metadata panel: every field against its source " + "-" * 25)
    for field, value in rows.items():
        if field in expected:
            verdict = "equal" if value == expected[field] else "DIFFERS"
            if verdict == "DIFFERS":
                FAILURES.append(f"metadata {field}")
            print(f"  {field:36s} | {str(value)[:72]:72s} | {verdict}")
        elif field == "evaluation method":
            checks = [
                "hold-out" in value,
                str(METRICS["evaluation"]["test_rows"]) in value,
                str(METRICS["split"]["train_rows"]) in value,
                str(METRICS["evaluation"]["threshold"]) in value,
            ]
            if not all(checks):
                FAILURES.append("metadata evaluation method")
            print(f"  {field:36s} | {value[:72]:72s} | {'equal' if all(checks) else 'DIFFERS'}")
            print(f"  {'':36s} | {'…' + value[72:]}".rstrip())
        elif field == "package versions":
            missing = [p for p in ("scikit-learn", "pandas", "numpy") if p not in value]
            if missing:
                FAILURES.append("metadata package versions")
            print(f"  {field:36s} | {value[:72]:72s} | {'equal' if not missing else 'DIFFERS'}")
            print(f"  {'':36s} | {'…' + value[72:]}".rstrip())
        else:
            print(f"  {field:36s} | {str(value)[:72]:72s} | (no single recorded source)")

    assert record.sha256 == _sha256(MODELS / "metrics.json"), "the record's digest is its file's"


# --------------------------------------------------------------- 4. EDA captions
def eda() -> None:
    summary = json.loads((MODELS / "eda" / "summary.json").read_text(encoding="utf-8"))
    panels = evaluation.eda_panels(summary)
    print("\n--- six EDA figures: artifact on disk, caption numbers from summary.json " + "-" * 8)
    if len(panels) != 6:
        FAILURES.append(f"{len(panels)} EDA panels, expected 6")
    paths = evaluation.figure_paths(MODELS)
    for panel in panels:
        path = paths[panel["file"]]
        present = path.is_file()
        if not present:
            FAILURES.append(f"missing figure {panel['file']}")
        print(f"  {panel['file']:34s} | {'present' if present else 'MISSING':8s} | "
              f"{path.stat().st_size if present else 0:>7,d} B | {panel['title'][:34]}")
        print(f"    caption: {panel['caption'][:150]}")
    zero = summary["class_counts"]["0"]
    if f"{zero:,}" not in panels[0]["caption"]:
        FAILURES.append("class-count caption does not quote summary.json")
    missing = evaluation.missing_figures(MODELS)
    print(f"  missing figures reported by src.evaluation: {missing or 'none'}")


# --------------------------------------------------------------- 5. feature importance
def importance() -> None:
    rows, note = evaluation.feature_importances(MODELS)
    print("\n--- feature importance: read from the verified artifact " + "-" * 23)
    print(f"  {note}")
    total = sum(row["importance"] for row in rows)
    print(f"  rows = {len(rows)}; sum of importances = {total:.6f} (normalised to 1)")
    for row in rows[:5]:
        print(f"  {row['feature']:10s} | importance {row['importance']:.6f} | "
              f"share {row['share of total'] * 100:.4f}%")
    order = MANIFEST["features"]["order"]
    if [row["feature"] for row in rows] and set(row["feature"] for row in rows) != set(order):
        FAILURES.append("importance features differ from the manifest's feature order")


# --------------------------------------------------------------- 6. figure titles
def titles() -> None:
    """The numbers inside the chart titles, which are display strings too.

    The S10 gate found a row count typed into the comparison chart's title at commit
    ``65b457e`` — the one place this probe never looked, because a title is a string rather
    than a table cell. Each title is now read back off the matplotlib axes and every number
    in it is matched against the record that owns it.
    """
    print("\n--- chart titles: every number inside a display string " + "-" * 22)
    test_rows = METRICS["evaluation"]["test_rows"]
    comparison = charts.comparison_figure(
        evaluation.comparison_rows(METRICS), test_rows
    ).axes[0].get_title()
    found = re.findall(r"\d[\d,]*", comparison)
    ok = found == [f"{test_rows:,}"]
    print(f"  comparison      | {comparison}")
    print(f"    numbers {found} vs evaluation.test_rows {test_rows:,}: {'OK' if ok else 'MISMATCH'}")
    moved = charts.comparison_figure(evaluation.comparison_rows(METRICS), 1234).axes[0].get_title()
    print(f"    mutation — the same figure handed test_rows=1234: {moved!r}")
    if "1,234" not in moved:
        FAILURES.append("comparison chart title does not follow test_rows")
    if not ok:
        FAILURES.append("comparison chart title")

    for panel in evaluation.confusion_matrices(METRICS):
        title = charts.confusion_figure(panel).axes[0].get_title()
        total = f"{int(panel['total']):,}"
        ok = total in re.findall(r"\d[\d,]*", title)
        print(f"  {panel['label']:15s} | {title}")
        print(f"    n = {total} (record): {'OK' if ok else 'MISMATCH'}")
        if not ok:
            FAILURES.append(f"{panel['label']} confusion title")

    rows, _note = evaluation.feature_importances(MODELS)
    title = charts.importance_figure(rows, total_features=len(rows)).axes[0].get_title()
    features = len(MANIFEST["features"]["order"])
    ok = str(features) in re.findall(r"\d+", title)
    print(f"  importance      | {title}")
    print(f"    feature count {features} (manifest): {'OK' if ok else 'MISMATCH'}")
    if not ok:
        FAILURES.append("importance chart title")


def main() -> int:
    print("S10 — trace every displayed number to models/metrics.json")
    print(f"  metrics.json        sha256 {_sha256(MODELS / 'metrics.json')}")
    print(f"  model_manifest.json sha256 {_sha256(MODELS / 'model_manifest.json')}")
    print(f"  best_pipeline.joblib sha256 {_sha256(MODELS / 'best_pipeline.joblib')}")
    print(f"  page modules        {', '.join(sorted(p.name for p in Path('src').glob('*.py') if 'evaluation' in p.name or p.name == 'charts.py'))}")
    comparison()
    confusion()
    metadata()
    eda()
    importance()
    titles()
    print("\n" + "=" * 78)
    if FAILURES:
        print(f"RESULT: FAIL — {len(FAILURES)} section(s) disagree: {FAILURES}")
        return 1
    print("RESULT: PASS — every compared value on the page equals its entry in metrics.json; "
          "0 mismatches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
