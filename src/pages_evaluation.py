"""Administration — model evaluation and insight panels (blueprint §6 routes; §9 SPRINT 10).

The page answers one question honestly: *what did the shipped model actually do, and where is
it weak?* It reads three generated artifacts and draws nothing it cannot cite:

* the comparison table, the three confusion matrices, the baseline and the metadata come from
  ``models/metrics.json`` (written by ``ml/evaluate.py``);
* the six EDA figures are the PNG artifacts ``ml/generate_eda.py`` wrote, and their captions
  quote ``models/eda/summary.json``;
* the feature-importance chart is computed from the deployed tree inside the verified artifact.

The page holds no statistic of its own — :mod:`src.evaluation` opens the records, and
:mod:`src.charts` draws figures from the same values, so the table and the picture cannot
disagree with the file.

Access is an administrator's. ``_guard`` calls :func:`src.security.require_role` with the
session token, so a user who forced this section would get a refusal and an audited
``auth.denied`` row, not the evaluation record: the ``if`` in ``app.py`` only chooses what to
draw.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import streamlit as st

from src import charts, evaluation, security

#: Said once at the top: where every number on the page comes from.
PROVENANCE_NOTICE = (
    "Every number below is read from the generated evaluation record at render time — nothing "
    "on this page is typed in. The comparison table, confusion matrices and metadata come from "
    "`models/metrics.json`; the EDA captions quote `models/eda/summary.json`; the "
    "feature-importance chart is computed from the deployed tree inside the verified artifact."
)

MATRIX_NOTICE = (
    "Each cell is labelled with its own name and count, and the two hatches separate correct "
    "from incorrect answers, so the matrix does not rely on colour. **Actual** is the row: "
    "TN and FP are accounts that did not default, FN and TP are accounts that did. The "
    "percentage is each cell's share of its actual class."
)

EDA_NOTICE = (
    "These are the six figures `ml/generate_eda.py` produced for the report, read from the "
    "image as artifacts. Each caption quotes the aggregate record they were drawn from."
)


def _guard(conn, token: str | None):
    """Server-side role check for this page. Returns ``None`` when the caller may not be here."""
    try:
        return security.require_role(conn, token, ("admin",), action="pages_evaluation.render")
    except security.AuthError as error:
        st.error(error.public_message)
        return None


def _draw(figure, alt: str) -> None:
    """Render one matplotlib figure and close it, so a rerun cannot accumulate figures."""
    st.pyplot(figure, clear_figure=True, alt=alt)


def _provenance(record: evaluation.MetricsRecord, manifest: Mapping[str, Any]) -> None:
    st.caption(
        f"Record: `{record.path.name}` sha256 `{record.sha256}`, generated "
        f"{record.generated_at}. Artifact: `{(manifest.get('artifact') or {}).get('path')}` "
        f"sha256 `{(manifest.get('artifact') or {}).get('sha256')}`, manifest written "
        f"{manifest.get('created_at')}."
    )


# ------------------------------------------------------------------ model comparison
def _comparison_section(metrics: Mapping[str, Any]) -> None:
    st.markdown("#### Model comparison")
    rows = evaluation.comparison_rows(metrics)
    selected = metrics["evaluation"].get("selected")
    st.caption(
        f"Cross-validation ran on the training rows only; the test columns are one score of "
        f"each candidate on the same held-out rows. The deployed model is "
        f"**{evaluation.MODEL_LABELS.get(selected, selected)}**, chosen by cross-validated F1 "
        "before the test rows were touched."
    )
    st.dataframe(rows, width="stretch", hide_index=True)
    st.caption(
        "CV columns are the mean and standard deviation over the recorded folds; the test "
        "columns are single values, so a difference smaller than the CV spread is not a real "
        "difference between two models."
    )

    with st.expander("Why this model was selected", expanded=False):
        for line in evaluation.selection_statements(metrics):
            st.markdown(f"- {line}" if line.startswith("•") else line)
        deltas = evaluation.delta_rows(metrics)
        if deltas:
            st.markdown("**Improvement over the constant-answer baseline**")
            st.dataframe(deltas, width="stretch", hide_index=True)

    _draw(
        charts.comparison_figure(rows, metrics["evaluation"].get("test_rows")),
        alt=(
            "Grouped bar chart of test accuracy, precision, recall, F1 and ROC-AUC for the "
            "logistic regression, decision tree and random forest, each bar labelled with its "
            "value."
        ),
    )
    # The leaders are read from the record, not asserted: the caption used to say which model
    # was ahead on which metric, which is a conclusion the page would have owned.
    leaders = evaluation.test_metric_leaders(metrics)
    lead_text = (
        "Highest held-out score per metric: "
        + "; ".join(
            f"{label} on {evaluation.METRIC_LABELS.get(key, key)} ({value:.3f})"
            for label, key, value in leaders
        )
        + ". "
        if leaders
        else ""
    )
    st.caption(
        "Same numbers as the table, drawn so the gap between the models is visible. "
        + lead_text
        + "A gap smaller than the CV spread above is not a real difference, and every model "
        "is far ahead of the constant-answer baseline on accuracy only because accuracy is "
        "dominated by the majority class."
    )


# ------------------------------------------------------------------ confusion matrices
def _confusion_section(metrics: Mapping[str, Any]) -> None:
    st.markdown("#### Confusion matrices — TN / FP / FN / TP")
    st.caption(MATRIX_NOTICE)
    panels = evaluation.confusion_matrices(metrics)
    if not panels:
        st.warning("The evaluation record contains no confusion matrix.")
        return
    for panel in panels:
        _draw(
            charts.confusion_figure(panel),
            alt=(
                f"Confusion matrix for {panel['label']}: TN {panel['tn']:,}, FP "
                f"{panel['fp']:,}, FN {panel['fn']:,}, TP {panel['tp']:,}, out of "
                f"{int(panel['total'] or 0):,} test accounts."
            ),
        )
    st.dataframe(evaluation.confusion_rows(metrics), width="stretch", hide_index=True)
    st.caption(
        "The arithmetic check column is the record's own recomputation of accuracy, "
        "precision, recall and F1 from each matrix; a non-zero delta would mean the metrics "
        "and the matrix disagree."
    )


# ------------------------------------------------------------------ EDA figures
def _eda_section(summary: Mapping[str, Any], models_dir) -> None:
    st.markdown("#### Exploratory data analysis")
    st.caption(EDA_NOTICE)
    paths = evaluation.figure_paths(models_dir)
    missing = set(evaluation.missing_figures(models_dir))
    for panel in evaluation.eda_panels(summary):
        st.markdown(f"##### {panel['title']}")
        path = paths.get(panel["file"])
        if panel["file"] in missing or path is None:
            st.warning(
                f"`{panel['file']}` is not present in this build, so this figure cannot be "
                "shown. The caption below still quotes the recorded aggregates."
            )
        else:
            st.image(str(path), caption=panel["caption"], width="stretch", alt=panel["alt"])
        if panel.get("table"):
            st.dataframe(panel["table"], width="stretch", hide_index=True)
            st.caption(
                "The heatmap encodes correlation as colour, so the strongest pairs are also "
                "listed as numbers here: the same information without relying on colour."
            )


# ------------------------------------------------------------------ feature importance
def _importance_section(models_dir) -> None:
    st.markdown("#### Feature importance")
    try:
        rows, note = evaluation.feature_importances(models_dir)
    except evaluation.EvaluationError as error:
        st.error(str(error))
        return
    st.caption(note)
    if not rows:
        st.info(
            "The selected model is not a tree, so there is no impurity-based importance to "
            "chart. The documented alternative is the coefficient table of the logistic "
            "regression candidate, which is not the deployed model."
        )
        return
    _draw(
        charts.importance_figure(rows, total_features=len(rows)),
        alt=(
            "Horizontal bar chart of the decision tree's feature importances as a share of "
            "total impurity reduction, each bar labelled with its percentage."
        ),
    )
    st.dataframe(rows, width="stretch", hide_index=True)
    st.caption(
        "Impurity-based importance says how much a feature contributed to the tree's splits; "
        "it is not a causal effect, and a feature the tree never split on scores zero."
    )


# ------------------------------------------------------------------ metadata and limits
def _metadata_section(record: evaluation.MetricsRecord, manifest: Mapping[str, Any], models_dir) -> None:
    st.markdown("#### Model metadata")
    rows = evaluation.metadata_rows(
        record.data,
        manifest,
        artifact_sha_now=evaluation.artifact_digest(models_dir),
        metrics_sha=record.sha256,
        metrics_path=record.path,
    )
    st.dataframe(rows, width="stretch", hide_index=True)
    st.caption(
        "Non-secret facts only. The artifact digest on disk is recomputed when this page "
        "renders; if it no longer matches the manifest, the model in service is not the model "
        "that was evaluated."
    )


def _limitations_section(metrics: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    st.markdown("#### Limitations, in plain language")
    for statement in evaluation.limitation_statements(metrics, manifest):
        st.markdown(f"- {statement}")


# ------------------------------------------------------------------ page
def render(conn, token: str | None, models_dir=None) -> None:
    """The Model evaluation page. Re-checks the admin role itself before it reads anything."""
    principal = _guard(conn, token)
    if principal is None:
        return

    st.markdown("### Model evaluation")
    st.caption(PROVENANCE_NOTICE)

    try:
        record = evaluation.load_metrics(models_dir)
        manifest = evaluation.load_manifest(models_dir)
        summary = evaluation.load_eda_summary(models_dir)
    except evaluation.EvaluationError as error:
        st.error(str(error))
        return

    _provenance(record, manifest)
    _comparison_section(record.data)
    _confusion_section(record.data)
    _eda_section(summary, models_dir)
    _importance_section(models_dir)
    _metadata_section(record, manifest, models_dir)
    _limitations_section(record.data, manifest)


__all__: Sequence[str] = [
    "EDA_NOTICE",
    "MATRIX_NOTICE",
    "PROVENANCE_NOTICE",
    "render",
]
