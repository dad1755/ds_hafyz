"""Sprint 10 gate: the admin evaluation page reports the record, it does not retype it.

Every claim this card makes is measured here rather than asserted:

* **the numbers are the record's.** Each cell of the comparison table and every confusion-matrix
  count is compared with ``models/metrics.json`` read independently of ``src.evaluation``; the
  metadata panel is compared with ``models/model_manifest.json`` and the artifact's own digest.
* **nothing is hard-coded.** The page is rendered against a *copy* of ``models/``, the copy's
  ``metrics.json`` is then rewritten with sentinel values, and the page is re-rendered: the
  displayed figures follow the file. A page holding its own copy of the numbers could not pass
  that. Separately, the draft-v3 statistics are searched for in the page's source, where none
  may appear.
* **the figures are drawn from the record.** The bar labels and matrix cells are read back out
  of the matplotlib artists and compared with the file, and the encoding is checked to be
  redundant (hatch differs wherever colour does).
* **a user role cannot reach the page.** The sidebar entry is absent for a user, and a forced
  call to ``pages_evaluation.render`` with a user's session is refused and audited.

``AppTest`` executes the real page, so these exercise the same code path a browser does.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src import charts, db, evaluation, security

REPO = Path(__file__).resolve().parents[1]
APP_PATH = REPO / "app.py"
MODELS_DIR = REPO / "models"

ADMIN = ("eval_admin", "amber-quartz-heron-91")
USER = ("eval_user", "violet-anchor-lamp-27")

#: The record, read here directly — the tests below never import it through ``src.evaluation``
#: when the point is that the module and the file agree.
METRICS = json.loads((MODELS_DIR / "metrics.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((MODELS_DIR / "model_manifest.json").read_text(encoding="utf-8"))

#: The figures the page draws: six EDA PNGs, three confusion matrices, the comparison chart and
#: the importance chart.
EXPECTED_IMAGES = 6 + 3 + 1 + 1

#: Statistics that exist only in the rejected v3 draft. None of these may appear in the page's
#: own source: the page has to read the record, and the record's real counts differ (4,431 /
#: 242 / 855 / 472 against the draft's 4,432 / 241 / 856 / 471).
DRAFT_V3_NUMBERS = (
    "4432",
    "4,432",
    "0.661517",
    "0.354936",
    "0.461991",
    "167,484.32",
    "167484.32",
    "51,223.33",
    "51223.33",
    "73,635.86",
    "73635.86",
    "81.72",
    "35.49",
    "46.20",
    "68.01",
    "77.88",
    "22.12",
)

#: The modules that make up the S10 surface.
PAGE_SOURCES = (
    REPO / "app.py",
    REPO / "src" / "pages_evaluation.py",
    REPO / "src" / "evaluation.py",
    REPO / "src" / "charts.py",
)


# --------------------------------------------------------------------------- fixtures
def _seed(conn: sqlite3.Connection, username: str, password: str, role: str) -> None:
    moment = db.to_iso(db.utcnow())
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO users (username, display_name, password_hash, role, is_active, "
            "must_change_password, created_at, updated_at, last_login_at) "
            "VALUES (?, ?, ?, ?, 1, 0, ?, ?, NULL)",
            (username, username.replace("_", " ").title(), security.hash_password(password),
             role, moment, moment),
        )


@pytest.fixture()
def app_db(tmp_path, monkeypatch):
    path = tmp_path / "eval.db"
    monkeypatch.setenv("APP_DB_PATH", str(path))
    connection = db.connect(path)
    try:
        db.migrate(connection)
        _seed(connection, *ADMIN, "admin")
        _seed(connection, *USER, "user")
    finally:
        connection.close()
    return path


@pytest.fixture()
def models_copy(tmp_path) -> Path:
    """A writable copy of ``models/`` so a test can change the record and watch the page."""
    target = tmp_path / "models"
    shutil.copytree(MODELS_DIR, target)
    return target


def _token(app_db: Path, who: tuple[str, str]) -> str:
    connection = db.connect(app_db)
    try:
        _principal, token = security.login(connection, *who)
        return token
    finally:
        connection.close()


def _render_page(app_db: Path, token: str, models_dir: Path | None = None) -> AppTest:
    """Run ``pages_evaluation.render`` in its own script, as the server would."""

    def page() -> None:
        import os

        from src import db, pages_evaluation

        connection = db.connect(os.environ["APP_DB_PATH"])
        try:
            pages_evaluation.render(
                connection,
                os.environ["PAGE_TOKEN"],
                os.environ.get("PAGE_MODELS_DIR") or None,
            )
        finally:
            connection.close()

    import os

    os.environ["APP_DB_PATH"] = str(app_db)
    os.environ["PAGE_TOKEN"] = token
    os.environ["PAGE_MODELS_DIR"] = str(models_dir) if models_dir else ""
    at = AppTest.from_function(page, default_timeout=180)
    return at.run()


def _sign_in(at: AppTest, who: tuple[str, str]) -> AppTest:
    at.text_input(key="login_username").set_value(who[0])
    at.text_input(key="login_password").set_value(who[1])
    return at.button[0].click().run()


# ------------------------------------------------------------------ 1. the record's numbers
def test_the_comparison_table_reports_every_recorded_metric() -> None:
    rows = {row["model"]: row for row in evaluation.comparison_rows(METRICS)}
    assert len(rows) == len(METRICS["candidates"]) + 1, "one row per candidate plus baseline"

    for name, candidate in METRICS["candidates"].items():
        row = rows[evaluation.MODEL_LABELS[name]]
        recorded = METRICS["evaluation"]["models"][name]
        cv = candidate["cv"]["metrics"]
        for column, key in (
            ("test accuracy", "accuracy"),
            ("test precision", "precision"),
            ("test recall", "recall"),
            ("test F1", "f1"),
            ("test ROC-AUC", "roc_auc"),
        ):
            assert row[column] == recorded["metrics"][key], f"{name} {key}"
        assert row["CV F1 mean"] == cv["f1"]["mean"]
        assert row["CV F1 std"] == cv["f1"]["std"]
        assert row["CV precision mean"] == cv["precision"]["mean"]
        assert row["CV recall mean"] == cv["recall"]["mean"]
        assert row["estimator"] == candidate["estimator"]
        assert row["threshold"] == f"{recorded['threshold']:.2f}"
        assert row["selected"] is (name == METRICS["evaluation"]["selected"])

    baseline = rows[
        "Baseline — " + str(METRICS["evaluation"]["baseline"]["description"])
    ]
    for column, key in (
        ("test accuracy", "accuracy"),
        ("test precision", "precision"),
        ("test recall", "recall"),
        ("test F1", "f1"),
        ("test ROC-AUC", "roc_auc"),
    ):
        assert baseline[column] == METRICS["evaluation"]["baseline"]["metrics"][key]
    # One column, one type: the baseline has no numeric threshold, and the table still renders.
    assert baseline["threshold"] == METRICS["evaluation"]["baseline"]["threshold"]
    assert all(isinstance(row["threshold"], str) for row in rows.values())


def test_the_confusion_matrices_are_the_recorded_counts() -> None:
    panels = {panel["key"]: panel for panel in evaluation.confusion_matrices(METRICS)}
    assert set(panels) == set(METRICS["evaluation"]["models"])

    for name, panel in panels.items():
        recorded = METRICS["evaluation"]["models"][name]["confusion_matrix"]
        for cell in ("tn", "fp", "fn", "tp"):
            assert panel[cell] == recorded[cell], f"{name} {cell}"
        assert panel["total"] == recorded["total"]
        assert panel["tn"] + panel["fp"] + panel["fn"] + panel["tp"] == panel["total"]

    rows = {row["model"]: row for row in evaluation.confusion_rows(METRICS)}
    for name in METRICS["evaluation"]["models"]:
        recorded = METRICS["evaluation"]["models"][name]["confusion_matrix"]
        row = rows[evaluation.MODEL_LABELS[name]]
        for cell in ("TN", "FP", "FN", "TP", "total"):
            assert row[cell] == recorded[cell.lower()]


def test_the_metadata_panel_names_the_deployed_model_dataset_and_versions() -> None:
    record = evaluation.load_metrics(MODELS_DIR)
    rows = {
        row["field"]: row["value"]
        for row in evaluation.metadata_rows(
            record.data,
            MANIFEST,
            artifact_sha_now=evaluation.artifact_digest(MODELS_DIR),
            metrics_sha=record.sha256,
            metrics_path=record.path,
        )
    }

    assert rows["selected model"] == METRICS["evaluation"]["selected"]
    assert rows["selected estimator"] == MANIFEST["model"]["estimator"]
    assert rows["trained / manifest written (UTC)"] == MANIFEST["created_at"]
    assert rows["evaluation record generated (UTC)"] == METRICS["generated_at"]
    assert rows["dataset sha256"] == MANIFEST["dataset"]["sha256"] == METRICS["dataset"]["sha256"]
    assert rows["decision threshold"] == str(MANIFEST["model"]["threshold"])
    assert "hold-out" in rows["evaluation method"]
    assert str(METRICS["evaluation"]["test_rows"]) in rows["evaluation method"]
    for package in ("scikit-learn", "pandas", "numpy"):
        assert package in rows["package versions"], package
    assert rows["artifact sha256 (manifest)"] == MANIFEST["artifact"]["sha256"]
    on_disk = hashlib.sha256((MODELS_DIR / "best_pipeline.joblib").read_bytes()).hexdigest()
    assert rows["artifact sha256 (on disk now)"] == on_disk
    assert rows["artifact matches its manifest"] == "True"
    assert record.sha256 == hashlib.sha256((MODELS_DIR / "metrics.json").read_bytes()).hexdigest()


def test_the_limitations_state_the_low_recall_in_plain_language() -> None:
    statements = evaluation.limitation_statements(METRICS, MANIFEST)
    text = " ".join(statements)
    matrix = METRICS["evaluation"]["models"][METRICS["evaluation"]["selected"]]["confusion_matrix"]
    recorded = METRICS["evaluation"]["models"][METRICS["evaluation"]["selected"]]["metrics"]

    assert "misses most defaults" in text.lower()
    assert f"{matrix['fn']:,}" in text, "the false-negative count is quoted"
    assert f"{recorded['recall']:.3f}" in text, "the recall is quoted"
    assert "not a credit decision" in text.lower()
    assert "calibrated" in text.lower(), "the uncalibrated probability is stated"
    # The baseline sentence is the record's own note, not a retyped statistic.
    assert METRICS["evaluation"]["baseline"]["note"] in text


# ------------------------------------------------------------------ 2. nothing is hard-coded
def test_the_page_follows_the_record_when_the_record_changes(
    app_db: Path, models_copy: Path
) -> None:
    """The strongest anti-hard-coding check: change the file, the page changes with it."""
    token = _token(app_db, ADMIN)

    first = _render_page(app_db, token, models_copy)
    assert not first.exception
    table = first.dataframe[0].value
    selected = METRICS["evaluation"]["selected"]
    label = evaluation.MODEL_LABELS[selected]
    before = float(
        table.loc[table["model"] == label, "test accuracy"].iloc[0]
    )
    assert before == METRICS["evaluation"]["models"][selected]["metrics"]["accuracy"]

    # Rewrite the copy with values that exist nowhere in the real record.
    record = json.loads((models_copy / "metrics.json").read_text(encoding="utf-8"))
    record["evaluation"]["models"][selected]["metrics"]["accuracy"] = 0.123456
    record["evaluation"]["models"][selected]["metrics"]["recall"] = 0.654321
    matrix = record["evaluation"]["models"][selected]["confusion_matrix"]
    matrix.update({"tn": 4001, "fp": 672, "fn": 700, "tp": 627})
    (models_copy / "metrics.json").write_text(json.dumps(record), encoding="utf-8")

    second = _render_page(app_db, token, models_copy)
    assert not second.exception
    table = second.dataframe[0].value
    after = float(table.loc[table["model"] == label, "test accuracy"].iloc[0])
    assert after == pytest.approx(0.123456), "the table followed the file"
    recall = float(table.loc[table["model"] == label, "test recall"].iloc[0])
    assert recall == pytest.approx(0.654321)

    counts = second.dataframe[2].value
    row = counts.loc[counts["model"] == label].iloc[0]
    assert (row["TN"], row["FP"], row["FN"], row["TP"]) == (4001, 672, 700, 627)
    # And the page's prose followed the record too, not just the table.
    prose = " ".join(markdown.value for markdown in second.markdown)
    assert "700" in prose and "0.654" in prose


def test_no_draft_v3_statistic_appears_in_the_page_source() -> None:
    """The rejected draft's figures must not be typed into the page's own code."""
    offenders: list[str] = []
    for path in PAGE_SOURCES:
        source = path.read_text(encoding="utf-8")
        for number in DRAFT_V3_NUMBERS:
            pattern = rf"(?<![\d.]){re.escape(number)}(?![\d.])"
            if re.search(pattern, source):
                offenders.append(f"{path.name}: {number}")
    assert not offenders, f"draft v3 statistics typed into the page: {offenders}"

    # The real counts are different from the draft's, and they only come from the record.
    real = METRICS["evaluation"]["models"]["decision_tree"]["confusion_matrix"]
    assert (real["tn"], real["fp"], real["fn"], real["tp"]) == (4431, 242, 855, 472)


def test_the_page_modules_hold_no_metric_literal_at_all() -> None:
    """Beyond the draft's numbers: no metric-shaped literal is stored in the S10 modules.

    The page's own constants are layout (dpi, font sizes, bar widths, axis limits). A float
    literal that is not one of those, and that looks like a score, would be a statistic the
    page owns rather than reads.
    """
    allowed = {
        # charts.py layout constants
        0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 0.4, 0.55, 0.45, 0.8, 0.7, 0.5, 0.16, 1.22,
        2.0, 3.05, 3.75, 3.1, 6.6, 3.6, 4.6, 200.0, 0.005, 100.0, 2.0,
        # font sizes / paddings / widths / axis limits
        5.4, 6.4, 6.8, 7.0, 7.5, 8.0, 8.5, 9.5, 0.2, 1.5,
    }
    offenders: list[str] = []
    for path in (REPO / "src" / "charts.py", REPO / "src" / "evaluation.py",
                 REPO / "src" / "pages_evaluation.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, float):
                if node.value in allowed:
                    continue
                offenders.append(f"{path.name}:{node.lineno} {node.value}")
    assert not offenders, f"numeric literals that are not layout: {offenders}"


# ------------------------------------------------------------------ 3. figures are real
def test_the_comparison_chart_labels_every_bar_with_the_recorded_value() -> None:
    rows = evaluation.comparison_rows(METRICS)
    figure = charts.comparison_figure(rows)
    labels = {text.get_text() for text in figure.axes[0].texts}

    for name in METRICS["evaluation"]["models"]:
        recorded = METRICS["evaluation"]["models"][name]["metrics"]
        for key in ("accuracy", "precision", "recall", "f1", "roc_auc"):
            assert f"{recorded[key]:.3f}" in labels, f"{name} {key}"
    # Colour is never the only difference between two models.
    assert len(set(charts.MODEL_HATCHES)) == len(charts.MODEL_HATCHES)
    assert "" in charts.MODEL_HATCHES and any(charts.MODEL_HATCHES)


def test_each_confusion_matrix_names_its_own_cells_and_counts() -> None:
    for panel in evaluation.confusion_matrices(METRICS):
        figure = charts.confusion_figure(panel)
        texts = " ".join(text.get_text() for text in figure.axes[0].texts)
        for cell, name in (("tn", "TN"), ("fp", "FP"), ("fn", "FN"), ("tp", "TP")):
            assert name in texts
            assert f"{panel[cell]:,}" in texts, f"{panel['key']} {cell}"
        hatches = {
            patch.get_hatch() for patch in figure.axes[0].patches if patch.get_hatch()
        }
        assert len(hatches) >= 2, "correct and incorrect cells differ by hatch, not only colour"


def test_each_confusion_matrix_puts_its_cells_on_the_row_and_column_they_belong_to() -> None:
    """The counts must sit under the axis label that names their class.

    A matrix that draws TN in the "actual = 1" row still prints every number correctly, so a
    test that only looks for the counts cannot catch it. This reads each cell's position off
    the artists and compares it with the tick label at that position.
    """
    for panel in evaluation.confusion_matrices(METRICS):
        figure = charts.confusion_figure(panel)
        axes = figure.axes[0]
        row_labels = {tick: label.get_text() for tick, label in enumerate(axes.get_yticklabels())}
        column_labels = {
            tick: label.get_text() for tick, label in enumerate(axes.get_xticklabels())
        }

        seen = set()
        for artist in axes.texts:
            name = artist.get_text().splitlines()[0]
            if name not in ("TN", "FP", "FN", "TP"):
                continue
            seen.add(name)
            x, y = artist.get_position()
            actual_class = "0" if name in ("TN", "FP") else "1"
            predicted_class = "0" if name in ("TN", "FN") else "1"
            assert row_labels[round(y)].startswith(actual_class), (
                f"{panel['key']}: {name} drawn on the row labelled "
                f"{row_labels[round(y)]!r}, but it is an actual-class-{actual_class} cell"
            )
            assert column_labels[round(x)].startswith(predicted_class), (
                f"{panel['key']}: {name} drawn in the column labelled "
                f"{column_labels[round(x)]!r}"
            )
        assert seen == {"TN", "FP", "FN", "TP"}, panel["key"]

        # And the count printed in each cell is the recorded one.
        printed = {artist.get_text().splitlines()[0]: artist.get_text().splitlines()[1]
                   for artist in axes.texts
                   if artist.get_text().splitlines()[0] in ("TN", "FP", "FN", "TP")}
        assert printed["TN"] == f"{panel['tn']:,}"
        assert printed["TP"] == f"{panel['tp']:,}"


def test_the_six_eda_figures_exist_and_their_captions_quote_the_record() -> None:
    summary = evaluation.load_eda_summary(MODELS_DIR)
    panels = evaluation.eda_panels(summary)
    assert len(panels) == 6
    assert evaluation.missing_figures(MODELS_DIR) == []

    paths = evaluation.figure_paths(MODELS_DIR)
    for panel in panels:
        assert paths[panel["file"]].is_file(), panel["file"]
        assert panel["caption"].strip(), "every figure carries a caption"
        assert panel["alt"] == panel["caption"], "the alt text carries the same content"

    zero = summary["class_counts"]["0"]
    assert f"{zero:,}" in panels[0]["caption"], "the class-count caption quotes summary.json"
    assert len(panels[5].get("table") or []) > 0, "the heatmap's pairs are also listed as numbers"


def test_the_rendered_page_shows_all_eleven_figures_and_no_warning(
    app_db: Path, models_copy: Path
) -> None:
    token = _token(app_db, ADMIN)
    at = _render_page(app_db, token, models_copy)

    assert not at.exception
    assert len(at.image) == EXPECTED_IMAGES, "six EDA figures, three matrices, two charts"
    assert not at.warning, [warning.value for warning in at.warning]
    assert not at.error
    # The record's own provenance is on screen, so a reader can check any number.
    captions = " ".join(caption.value for caption in at.caption)
    record_sha = hashlib.sha256((models_copy / "metrics.json").read_bytes()).hexdigest()
    assert record_sha in captions
    assert MANIFEST["artifact"]["sha256"] in captions


# ------------------------------------------------------------------ 4. a user is refused
def test_a_user_role_does_not_see_the_evaluation_entry(app_db: Path) -> None:
    at = AppTest.from_file(str(APP_PATH), default_timeout=180).run()
    at = _sign_in(at, USER)
    assert not at.exception
    options = list(at.sidebar.radio[0].options)
    assert "Model evaluation" not in options
    assert "User management" not in options


def test_a_user_role_is_refused_when_the_page_is_forced(app_db: Path) -> None:
    token = _token(app_db, USER)
    at = _render_page(app_db, token)

    assert not at.exception
    assert at.error, "the forced call must render a refusal"
    assert "permission" in at.error[0].value.lower()
    assert len(at.dataframe) == 0, "no evaluation record is rendered"
    assert len(at.image) == 0, "no figure is rendered"

    connection = db.connect(app_db)
    try:
        row = connection.execute(
            "SELECT action, non_sensitive_details FROM audit_events "
            "WHERE action = 'auth.denied' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        connection.close()
    assert row is not None, "the refusal is audited"
    assert "pages_evaluation.render" in row["non_sensitive_details"]


def test_an_anonymous_caller_is_refused_too(app_db: Path) -> None:
    at = _render_page(app_db, "")
    assert not at.exception
    assert at.error
    assert len(at.dataframe) == 0
    assert len(at.image) == 0
