#!/usr/bin/env python3
"""Six EDA figures and the descriptive-statistics summary for the seed dataset (S3).

Regenerates, from `data/UCI_Credit_Card.csv` alone, exactly these six PNGs:

1. ``01_target_class_distribution.png`` — class balance of the target.
2. ``02_age_by_class.png``           — age distribution per class (boxplot).
3. ``03_limit_bal_by_class.png``     — credit limit per class (boxplot, NTD).
4. ``04_default_rate_by_pay0.png``   — default rate per September repayment status.
5. ``05_default_rate_by_education.png`` — default rate per education code.
6. ``06_correlation_heatmap.png``    — Pearson correlation of the financial columns.

It also writes ``summary.json`` (counts, descriptive statistics, category counts and the
strongest correlations) so every number quoted in a caption in `docs/report_evidence.md`
can be traced to a machine-produced file.

The plots are written to disk as files; nothing is held in memory for the app, so a
restart (or a fresh container) reads the same PNGs.

Usage:
    python -m ml.generate_eda --csv data/UCI_Credit_Card.csv --out models/eda
    python3 ml/generate_eda.py --csv data/UCI_Credit_Card.csv --out models/eda

The column contract (names, units, code labels, target semantics) comes from
`ml/schema.py` — this script never defines a column of its own.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: write files, never open a window

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

try:  # `python -m ml.generate_eda` from the repository root
    from ml.schema import FEATURES, TARGET_COLUMN, TARGET_LABELS
except ModuleNotFoundError:  # `python3 ml/generate_eda.py` from the repository root
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from ml.schema import FEATURES, TARGET_COLUMN, TARGET_LABELS

# --------------------------------------------------------------------------- presentation

#: 3.75 in at 200 dpi = 750 px wide, so the figures stay legible when the app renders
#: them at a 375 px viewport (S7/S10). Font sizes are sized for that downscale.
FIGSIZE = (3.75, 3.05)
FIGSIZE_HEATMAP = (4.7, 4.1)
DPI = 200
CLASS_COLORS = {0: "#4C72B0", 1: "#C44E52"}
INK = "#1a1a1a"
MUTED = "#555555"

#: Financial columns for the correlation heatmap: the credit limit, the six statement
#: balances and the six payment amounts. Repayment-status codes are ordinal, not
#: amounts, so a Pearson coefficient on them would be meaningless and they are excluded.
FINANCIAL_COLUMNS = ["LIMIT_BAL"] + [f"BILL_AMT{i}" for i in range(1, 7)] + [
    f"PAY_AMT{i}" for i in range(1, 7)
]

#: Short tick labels for the 13×13 heatmap (defined in `docs/report_evidence.md`).
SHORT_LABELS = {"LIMIT_BAL": "LMT"} | {
    f"BILL_AMT{i}": f"B{i}" for i in range(1, 7)
} | {f"PAY_AMT{i}": f"A{i}" for i in range(1, 7)}


def apply_style() -> None:
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
            "axes.prop_cycle": matplotlib.cycler(color=list(CLASS_COLORS.values())),
        }
    )


def source_line(n_rows: int) -> str:
    """Attribution line required by blueprint §9 SPRINT 3 (title, axes, source, units)."""
    return (
        f"Source: UCI_Credit_Card.csv — {n_rows:,} accounts, Taiwan, Apr–Sep 2005"
    )


def finish(
    fig: plt.Figure, out: Path, n_rows: int, *, source: bool = True, note: str | None = None
) -> Path:
    """Add the optional code note and source line, tighten the layout, write the PNG."""
    bottom = 0.0
    if source:
        fig.text(0.008, 0.008, source_line(n_rows), fontsize=5.6, color=MUTED, ha="left")
        bottom = 0.045
    if note:
        fig.text(0.008, 0.032 if source else 0.008, note, fontsize=5.6, color=MUTED, ha="left")
        bottom = 0.075 if source else 0.045
    if bottom:
        fig.tight_layout(rect=(0, bottom, 1, 1))
    else:
        fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    # Explicit metadata keeps the bytes reproducible: no timestamp, no host path.
    fig.savefig(
        out,
        format="png",
        dpi=DPI,
        metadata={"Software": "aihubcampus ml/generate_eda.py"},
    )
    plt.close(fig)
    return out


def thousands(value: float, _pos: object = None) -> str:
    return f"{value:,.0f}"


# --------------------------------------------------------------------------- figures


def plot_target_distribution(df: pd.DataFrame, out: Path) -> Path:
    counts = df[TARGET_COLUMN].value_counts().sort_index()
    total = int(counts.sum())
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    positions = [0, 1]
    bars = ax.bar(
        positions,
        [counts.get(0, 0), counts.get(1, 0)],
        width=0.55,
        color=[CLASS_COLORS[0], CLASS_COLORS[1]],
    )
    for bar, value in zip(bars, [counts.get(0, 0), counts.get(1, 0)], strict=True):
        ax.annotate(
            f"{value:,}\n({value / total:.1%})",
            xy=(bar.get_x() + bar.get_width() / 2, value),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    ax.set_xticks(positions)
    ax.set_xticklabels(
        [f"0\n{TARGET_LABELS[0]}", f"1\n{TARGET_LABELS[1]}"], fontsize=7.5
    )
    ax.set_xlabel("Target: default next month", labelpad=2)
    ax.set_ylabel("Accounts (count)")
    ax.set_title("Class distribution: 22.1% defaulted", pad=8)
    ax.set_ylim(0, total * 0.95)
    ax.yaxis.set_major_formatter(FuncFormatter(thousands))
    return finish(fig, out, total)


def _boxplot_by_class(
    df: pd.DataFrame,
    column: str,
    ylabel: str,
    title: str,
    out: Path,
    *,
    formatter: FuncFormatter | None = None,
) -> Path:
    groups = [df.loc[df[TARGET_COLUMN] == k, column].to_numpy() for k in (0, 1)]
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    box = ax.boxplot(
        groups,
        widths=0.45,
        patch_artist=True,
        showfliers=False,  # outliers are described in the caption, not drawn over the box
        medianprops={"color": INK, "linewidth": 1.2},
        whiskerprops={"color": MUTED},
        capprops={"color": MUTED},
        boxprops={"edgecolor": MUTED},
    )
    for patch, colour in zip(box["boxes"], [CLASS_COLORS[0], CLASS_COLORS[1]], strict=True):
        patch.set_facecolor(colour)
        patch.set_alpha(0.75)
    ax.set_xticks([1, 2])
    ax.set_xticklabels(["0\nno default", "1\ndefault"], fontsize=7.5)
    ax.set_xlabel("Target: default next month", labelpad=2)
    ax.set_ylabel(ylabel)
    if formatter is not None:
        ax.yaxis.set_major_formatter(formatter)
    ax.set_title(title, pad=6)
    return finish(fig, out, len(df))


def plot_age_by_class(df: pd.DataFrame, out: Path) -> Path:
    return _boxplot_by_class(
        df,
        "AGE",
        "Age (years)",
        "Age spread is similar in both classes",
        out,
    )


def plot_limit_bal_by_class(df: pd.DataFrame, out: Path) -> Path:
    return _boxplot_by_class(
        df,
        "LIMIT_BAL",
        "Credit limit (NTD)",
        "Defaulters hold smaller credit limits",
        out,
        formatter=FuncFormatter(thousands),
    )


def _rate_chart(
    df: pd.DataFrame,
    column: str,
    codes: list[int],
    xlabel: str,
    title: str,
    out: Path,
    note: str,
) -> Path:
    subset = df[df[column].isin(codes)]
    grouped = subset.groupby(column, observed=True)[TARGET_COLUMN].agg(["count", "mean"])
    grouped = grouped.reindex(codes)
    rates = (grouped["mean"] * 100).fillna(0.0)
    counts = grouped["count"].fillna(0).astype(int)

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    bars = ax.bar(
        range(len(codes)),
        rates.to_numpy(),
        width=0.68,
        color=CLASS_COLORS[1],
        alpha=0.85,
    )
    ceiling = float(rates.max()) if float(rates.max()) > 0 else 1.0
    for bar, rate in zip(bars, rates.to_numpy(), strict=True):
        ax.annotate(
            f"{rate:.0f}",
            xy=(bar.get_x() + bar.get_width() / 2, rate),
            xytext=(0, 2),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=6.5,
        )
    # Codes only on the axis: the meanings go in the footnote, because two-line
    # labels for 7–11 categories cannot stay legible at a 375 px viewport.
    ax.set_xticks(range(len(codes)))
    ax.set_xticklabels([str(code) for code in codes], fontsize=7.5)
    ax.set_xlabel(xlabel, labelpad=2)
    ax.set_ylabel("Default rate (%)")
    ax.set_ylim(0, min(100.0, ceiling * 1.22))
    ax.set_title(title, pad=6)
    finish(fig, out, len(df), note=note)
    return out


def plot_default_rate_by_pay0(df: pd.DataFrame, out: Path) -> Path:
    codes = sorted(df["PAY_0"].unique().tolist())
    return _rate_chart(
        df,
        "PAY_0",
        codes,
        "PAY_0 code (Sep 2005 repayment status)",
        "Default rate climbs with repayment delay",
        out,
        note="Codes: −2 no consumption, −1 paid in full, 0 revolving, 1–8 months delay",
    )


def plot_default_rate_by_education(df: pd.DataFrame, out: Path) -> Path:
    codes = sorted(df["EDUCATION"].unique().tolist())
    return _rate_chart(
        df,
        "EDUCATION",
        codes,
        "EDUCATION code",
        "Default rate by education code",
        out,
        note="Codes: 1 grad school, 2 university, 3 high school, 4 others, 0/5/6 unknown",
    )


def plot_correlation_heatmap(df: pd.DataFrame, out: Path) -> Path:
    corr = df[FINANCIAL_COLUMNS].corr(method="pearson")
    labels = [SHORT_LABELS[name] for name in FINANCIAL_COLUMNS]
    fig, ax = plt.subplots(figsize=FIGSIZE_HEATMAP, dpi=DPI)
    # No cell text: 13×13 numbers are unreadable at 375 px, so the colour pattern
    # carries the shape and the caption quotes the coefficients that matter.
    image = ax.imshow(corr.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=6.5, rotation=90)
    ax.set_yticklabels(labels, fontsize=6.5)
    ax.spines[:].set_visible(False)
    ax.set_title("Financial columns correlate in two blocks", pad=6)
    ax.set_xlabel(
        "LMT = LIMIT_BAL; B1–B6 = BILL_AMT1–6; A1–A6 = PAY_AMT1–6 (NTD)",
        fontsize=5.8,
        labelpad=2,
    )
    bar = fig.colorbar(image, ax=ax, fraction=0.046, pad=0.03)
    bar.set_label("Pearson r", fontsize=7)
    bar.ax.tick_params(labelsize=6.5)
    return finish(fig, out, len(df))


# --------------------------------------------------------------------------- statistics


def descriptive_summary(df: pd.DataFrame) -> dict:
    """Machine-produced numbers behind every caption in `docs/report_evidence.md`."""
    target = df[TARGET_COLUMN]
    counts = {str(int(k)): int(v) for k, v in target.value_counts().sort_index().items()}
    stats: dict[str, dict[str, float | int]] = {}
    for name in FEATURES:
        series = df[name]
        stats[name] = {
            "count": int(series.count()),
            "min": float(series.min()),
            "max": float(series.max()),
            "mean": round(float(series.mean()), 4),
            "median": round(float(series.median()), 4),
            "q25": round(float(series.quantile(0.25)), 4),
            "q75": round(float(series.quantile(0.75)), 4),
            "std": round(float(series.std()), 4),
        }

    def group_stats(column: str, codes: list[int]) -> dict[str, dict[str, float | int]]:
        out: dict[str, dict[str, float | int]] = {}
        for code in codes:
            mask = df[column] == code
            n = int(mask.sum())
            out[str(code)] = {
                "count": n,
                "share_pct": round(n / len(df) * 100, 2),
                "default_count": int(target[mask].sum()),
                "default_rate_pct": round(float(target[mask].mean() * 100), 2) if n else 0.0,
            }
        return out

    # Per-class distributions for the two boxplots, so each caption number is traceable.
    numeric_by_target: dict[str, dict[str, dict[str, float | int]]] = {}
    for column in ("AGE", "LIMIT_BAL"):
        numeric_by_target[column] = {}
        for code in (0, 1):
            series = df.loc[target == code, column]
            numeric_by_target[column][str(code)] = {
                "count": int(series.count()),
                "min": float(series.min()),
                "q25": round(float(series.quantile(0.25)), 4),
                "median": round(float(series.median()), 4),
                "mean": round(float(series.mean()), 4),
                "q75": round(float(series.quantile(0.75)), 4),
                "max": float(series.max()),
            }

    corr = df[FINANCIAL_COLUMNS].corr(method="pearson")
    pairs = []
    for i, left in enumerate(FINANCIAL_COLUMNS):
        for right in FINANCIAL_COLUMNS[i + 1 :]:
            value = float(corr.loc[left, right])
            pairs.append({"a": left, "b": right, "r": round(value, 4)})
    pairs.sort(key=lambda item: abs(item["r"]), reverse=True)

    return {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "features": len(FEATURES),
        "class_counts": counts,
        "class_share_pct": {
            str(k): round(v / len(df) * 100, 2) for k, v in counts.items()
        },
        "missing_cells": int(df.isna().sum().sum()),
        "descriptive": stats,
        "pay0_by_target": group_stats("PAY_0", sorted(df["PAY_0"].unique().tolist())),
        "education_by_target": group_stats(
            "EDUCATION", sorted(df["EDUCATION"].unique().tolist())
        ),
        "marriage_by_target": group_stats(
            "MARRIAGE", sorted(df["MARRIAGE"].unique().tolist())
        ),
        "correlation_columns": FINANCIAL_COLUMNS,
        "numeric_by_target": numeric_by_target,
        "strongest_correlations": pairs[:8],
        "correlation_matrix": {
            row: {col: round(float(corr.loc[row, col]), 4) for col in FINANCIAL_COLUMNS}
            for row in FINANCIAL_COLUMNS
        },
    }


def load(  # noqa: D401 - small helper
    csv_path: Path,
) -> pd.DataFrame:
    frame = pd.read_csv(csv_path)
    # The seed file writes some amounts as 5e+05 (4,262 cells, all whole numbers).
    # pandas reads those as float; casting keeps the figures and statistics integral.
    for column in frame.columns:
        if column != TARGET_COLUMN:
            frame[column] = frame[column].astype("int64")
    return frame


PLOTS = (
    ("01_target_class_distribution.png", plot_target_distribution),
    ("02_age_by_class.png", plot_age_by_class),
    ("03_limit_bal_by_class.png", plot_limit_bal_by_class),
    ("04_default_rate_by_pay0.png", plot_default_rate_by_pay0),
    ("05_default_rate_by_education.png", plot_default_rate_by_education),
    ("06_correlation_heatmap.png", plot_correlation_heatmap),
)


def print_summary(summary: dict) -> None:
    total = summary["rows"]
    print(f"rows / columns      : {total:,} / {summary['columns']}")
    print(f"features            : {summary['features']}")
    print(f"missing cells       : {summary['missing_cells']}")
    for label, key in ((0, "0"), (1, "1")):
        count = summary["class_counts"][key]
        print(
            f"class {label} ({TARGET_LABELS[label]:<20}): {count:>6,} "
            f"({summary['class_share_pct'][key]:.2f}%)"
        )
    print()
    print(f"{'column':<12}{'min':>10}{'q25':>10}{'median':>10}{'mean':>12}{'q75':>10}{'max':>10}")
    for name in FEATURES:
        row = summary["descriptive"][name]
        print(
            f"{name:<12}{row['min']:>10,.0f}{row['q25']:>10,.0f}{row['median']:>10,.0f}"
            f"{row['mean']:>12,.2f}{row['q75']:>10,.0f}{row['max']:>10,.0f}"
        )
    print()
    for column in ("AGE", "LIMIT_BAL"):
        for code in ("0", "1"):
            row = summary["numeric_by_target"][column][code]
            unit = "years" if column == "AGE" else "NTD"
            print(
                f"{column:<10} class {code}  n={row['count']:>6,}  min={row['min']:>10,.0f}"
                f"  q25={row['q25']:>10,.0f}  median={row['median']:>10,.0f}"
                f"  mean={row['mean']:>12,.2f}  q75={row['q75']:>10,.0f}"
                f"  max={row['max']:>10,.0f}  ({unit})"
            )
    print()
    for key, title in (
        ("pay0_by_target", "PAY_0 (Sep 2005) by target"),
        ("education_by_target", "EDUCATION by target"),
        ("marriage_by_target", "MARRIAGE by target"),
    ):
        print(title)
        for code, row in summary[key].items():
            print(
                f"  code {code:>3}  n={row['count']:>6,}  share={row['share_pct']:>5.2f}%"
                f"  defaults={row['default_count']:>5,}  rate={row['default_rate_pct']:>5.2f}%"
            )
        print()
    print("strongest Pearson correlations (financial columns)")
    for pair in summary["strongest_correlations"]:
        print(f"  {pair['a']:<10} ~ {pair['b']:<10} r = {pair['r']:+.3f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate the six S3 EDA figures and the descriptive summary."
    )
    parser.add_argument("--csv", default="data/UCI_Credit_Card.csv", type=Path)
    parser.add_argument("--out", default="models/eda", type=Path)
    parser.add_argument(
        "--quiet", action="store_true", help="write the files without printing the summary"
    )
    args = parser.parse_args(argv)

    if not args.csv.is_file():
        print(f"ERROR: CSV not found: {args.csv}", file=sys.stderr)
        return 2

    apply_style()
    df = load(args.csv)
    args.out.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for filename, plotter in PLOTS:
        written.append(plotter(df, args.out / filename))

    summary = descriptive_summary(df)
    summary_path = args.out / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    if not args.quiet:
        print_summary(summary)
        print()
    print(f"wrote {len(written)} figures to {args.out}/")
    for path in written + [summary_path]:
        print(f"  {path.name:<36}{path.stat().st_size:>8,} B")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
