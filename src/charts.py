"""Accessible figures for the admin evaluation page (blueprint §9 SPRINT 10).

Three rules, because the card requires colour to be redundant rather than the only carrier of
meaning:

* **every mark is labelled with its own value.** A bar carries its number above it; a
  confusion-matrix cell carries its name (TN/FP/FN/TP), its count and its share of the actual
  class. Nothing on these figures can only be read by seeing a colour.
* **shape differs where colour differs.** The three models are hatched ``solid`` / ``///`` /
  ``...``, and correct and incorrect cells of a matrix use two different hatches. The palette
  is the Okabe–Ito colour-blind-safe set, and it is never the only difference between two
  categories.
* **text is drawn on a light fill.** Cell text is always dark ink on a pale tint, so contrast
  survives any colour-vision deficiency, a projector and a 375 px screen.

The figures are built from the artifacts at render time — no PNG is read here — so the page
cannot show a chart that disagrees with ``models/metrics.json``. ``ml/generate_eda.py`` draws
the six EDA figures in the same visual language, and those *are* read from disk as artifacts.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")  # a server-rendered figure never needs a window; must precede pyplot

import matplotlib.pyplot as plt  # noqa: E402  (backend selection must come first)
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

#: 3.75 in at 200 dpi = 750 px wide, the width ``ml/generate_eda.py`` uses so the figures stay
#: legible at a 375 px viewport.
FIGSIZE = (3.75, 3.05)
FIGSIZE_WIDE = (6.6, 3.1)
FIGSIZE_IMPORTANCE = (4.6, 3.6)
DPI = 200

INK = "#1a1a1a"
MUTED = "#555555"
#: Okabe–Ito colour-blind-safe palette.
BLUE = "#0072B2"
VERMILLION = "#D55E00"
GREEN = "#009E73"
SKY = "#56B4E9"

#: One hatch per model, so the three series differ by shape as well as by colour.
MODEL_HATCHES = ("", "///", "...")
MODEL_COLOURS = (BLUE, VERMILLION, SKY)

#: Pale fills for a confusion matrix: correct cells and error cells.
CORRECT_FILL = "#D6E9F5"
ERROR_FILL = "#FBE0D0"

#: The held-out metrics the comparison chart plots, in reading order.
COMPARISON_METRICS = (
    ("test accuracy", "accuracy"),
    ("test precision", "precision"),
    ("test recall", "recall"),
    ("test F1", "F1"),
    ("test ROC-AUC", "ROC-AUC"),
)


#: Number words, so the comparison title's candidate count comes from the plotted series.
_COUNT_WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six"}


def apply_style() -> None:
    """Match the EDA figures' typography so the admin page looks like one report."""
    plt.rcParams.update(
        {
            "figure.dpi": DPI,
            "savefig.dpi": DPI,
            "font.size": 8,
            "font.family": "DejaVu Sans",
            "axes.titlesize": 9.5,
            "axes.titleweight": "bold",
            "axes.labelsize": 8.5,
            "axes.edgecolor": MUTED,
            "axes.labelcolor": INK,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "text.color": INK,
            "legend.fontsize": 7.5,
            "legend.frameon": False,
            "axes.grid": False,
        }
    )


def _model_series(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The candidate rows the comparison chart can plot (the baseline has nulls)."""
    return [
        row
        for row in rows
        if not str(row.get("model", "")).startswith("Baseline")
        and any(row.get(column) is not None for column, _ in COMPARISON_METRICS)
    ]


def comparison_figure(
    rows: Sequence[Mapping[str, Any]], test_rows: int | None = None
) -> Figure:
    """Grouped bars: the three candidates' held-out metrics, each bar labelled with its value.

    ``test_rows`` is ``evaluation.test_rows`` from the record. The title quotes it rather than
    repeating a count, so the figure cannot claim a row count the record does not hold — the
    S10 gate caught exactly that, a ``6,000`` typed into this title. Both numbers in the title
    come from data: the candidate count from ``series``, the row count from the record.
    """
    apply_style()
    series = _model_series(rows)
    figure, axes = plt.subplots(figsize=FIGSIZE_WIDE, dpi=DPI)
    if not series:
        axes.text(0.5, 0.5, "no candidate metrics recorded", ha="center", va="center")
        axes.set_axis_off()
        return figure

    width = 0.8 / max(len(series), 1)
    positions = range(len(COMPARISON_METRICS))
    for index, row in enumerate(series):
        offsets = [position + (index - (len(series) - 1) / 2) * width for position in positions]
        values = [
            float(row[column]) if row.get(column) is not None else 0.0
            for column, _ in COMPARISON_METRICS
        ]
        bars = axes.bar(
            offsets,
            values,
            width=width,
            color=MODEL_COLOURS[index % len(MODEL_COLOURS)],
            hatch=MODEL_HATCHES[index % len(MODEL_HATCHES)],
            edgecolor=INK,
            linewidth=0.4,
            label=str(row.get("model")),
            zorder=3,
        )
        for bar, value in zip(bars, values, strict=True):
            axes.annotate(
                f"{value:.3f}",
                xy=(bar.get_x() + bar.get_width() / 2, value),
                xytext=(0, 2),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=5.4,
                rotation=90,
                color=INK,
            )
    axes.set_xticks(list(positions))
    axes.set_xticklabels([label for _, label in COMPARISON_METRICS], fontsize=7)
    axes.set_ylim(0, 1.0)
    axes.set_ylabel("Score on the held-out test rows")
    title = f"{_COUNT_WORDS.get(len(series), str(len(series)))} candidates"
    if test_rows:
        title += f" on the same {int(test_rows):,} test rows"
    axes.set_title(title, pad=8)
    axes.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=3)
    figure.tight_layout()
    return figure


def _contrast_ink() -> str:
    """Dark ink for every pale fill used here; kept as a function so the rule is explicit."""
    return INK


def confusion_figure(panel: Mapping[str, Any]) -> Figure:
    """A 2×2 confusion matrix whose cells carry their name, count and share of the actual class."""
    apply_style()
    tn, fp = int(panel["tn"]), int(panel["fp"])
    fn, tp = int(panel["fn"]), int(panel["tp"])
    actual_0, actual_1 = tn + fp, fn + tp
    # Row 0 is actual class 0 and row 1 is actual class 1, drawn bottom-up so the tick label at
    # y=0 is the label of the cells on that row. Getting this pairing wrong would put TN under
    # the "default" row while the numbers still looked plausible, which is why
    # tests/test_evaluation.py reads the cell positions back off the artists.
    cells = [
        # (row, column, name, count, share of its actual class, fill)
        (0, 0, "TN", tn, tn / actual_0 if actual_0 else 0.0, CORRECT_FILL),
        (0, 1, "FP", fp, fp / actual_0 if actual_0 else 0.0, ERROR_FILL),
        (1, 0, "FN", fn, fn / actual_1 if actual_1 else 0.0, ERROR_FILL),
        (1, 1, "TP", tp, tp / actual_1 if actual_1 else 0.0, CORRECT_FILL),
    ]
    peak = max(cell[3] for cell in cells) or 1

    figure, axes = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    for row, column, name, count, share, fill in cells:
        # A faint intensity cue on top of the flat fill: still visible in greyscale, but the
        # printed number is what carries the magnitude.
        alpha = 0.55 + 0.45 * (count / peak)
        axes.add_patch(
            plt.Rectangle(
                (column - 0.5, row - 0.5),
                1,
                1,
                facecolor=fill,
                alpha=alpha,
                edgecolor="white",
                linewidth=2,
                hatch="//" if name in ("TN", "TP") else "..",
                zorder=2,
            )
        )
        axes.text(
            column,
            row,
            f"{name}\n{count:,}\n{share:.1%}",
            ha="center",
            va="center",
            fontsize=8.5,
            fontweight="bold",
            color=_contrast_ink(),
            zorder=4,
        )
    labels = panel.get("labels") or []
    short = [str(label).replace(" next month", "") for label in labels]
    if len(short) != 2:
        short = ["0 = no default", "1 = default"]
    axes.set_xlim(-0.5, 1.5)
    axes.set_ylim(-0.5, 1.5)
    axes.set_xticks([0, 1])
    axes.set_yticks([0, 1])
    axes.set_xticklabels(short, fontsize=7)
    axes.set_yticklabels(short, fontsize=7)
    axes.set_xlabel("Predicted label", labelpad=2)
    axes.set_ylabel("Actual label", labelpad=2)
    axes.set_title(
        f"{panel.get('label')} — threshold {panel.get('threshold')} (n = {int(panel.get('total') or 0):,})",
        pad=8,
    )
    for spine in axes.spines.values():
        spine.set_visible(False)
    axes.tick_params(length=0)
    figure.tight_layout()
    return figure


def importance_figure(
    rows: Sequence[Mapping[str, Any]], *, top: int = 15, total_features: int | None = None
) -> Figure:
    """Horizontal bars: the deployed tree's importances, each labelled with its share."""
    apply_style()
    shown = list(rows)[:top]
    figure, axes = plt.subplots(figsize=FIGSIZE_IMPORTANCE, dpi=DPI)
    if not shown:
        axes.text(0.5, 0.5, "no importances recorded", ha="center", va="center")
        axes.set_axis_off()
        return figure

    names = [str(row["feature"]) for row in shown][::-1]
    shares = [float(row["share of total"]) * 100.0 for row in shown][::-1]
    positions = range(len(names))
    bars = axes.barh(
        list(positions),
        shares,
        height=0.7,
        color=BLUE,
        edgecolor=INK,
        linewidth=0.4,
        zorder=3,
    )
    for bar, share in zip(bars, shares, strict=True):
        axes.annotate(
            f"{share:.2f}%",
            xy=(share, bar.get_y() + bar.get_height() / 2),
            xytext=(3, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=6.4,
        )
    axes.set_yticks(list(positions))
    axes.set_yticklabels(names, fontsize=6.8)
    axes.set_xlim(0, max(shares) * 1.22 if max(shares) else 1.0)
    axes.xaxis.set_major_formatter(FuncFormatter(lambda value, _pos: f"{value:.0f}%"))
    axes.set_xlabel("Share of total impurity reduction", labelpad=2)
    title = "Decision-tree feature importance"
    if total_features and total_features > len(shown):
        title += f" (top {len(shown)} of {total_features})"
    axes.set_title(title, pad=8)
    figure.tight_layout()
    return figure


__all__ = [
    "COMPARISON_METRICS",
    "MODEL_COLOURS",
    "MODEL_HATCHES",
    "apply_style",
    "comparison_figure",
    "confusion_figure",
    "importance_figure",
]
