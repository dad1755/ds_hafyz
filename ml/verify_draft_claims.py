#!/usr/bin/env python3
"""Verify the numeric claims made by the draft report (.docx) against the CSV.

Sprint 0 asks for a claim-by-claim classification: which statements in the draft
are verified now by executed code, and which remain unverified until the sprint
that produces them (model metrics, test cases, deployment). Standard library
only so it runs before the ML environment exists.

Quantiles use numpy/pandas default 'linear' interpolation on (n-1) so the
numbers are comparable with the draft's Table 8.

Usage:
    python3 ml/verify_draft_claims.py --csv data/UCI_Credit_Card.csv
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict

TARGET = "default.payment.next.month"


def load(path: str) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append({key: float(value) for key, value in row.items()})
    return rows


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def stdev(values: list[float]) -> float:
    """Sample standard deviation (ddof=1), matching pandas .std()."""
    m = mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def quantile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    position = p * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (position - low) * (ordered[high] - ordered[low])


def pearson(a: list[float], b: list[float]) -> float:
    ma, mb = mean(a), mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/UCI_Credit_Card.csv")
    parser.add_argument("--tolerance", type=float, default=0.01,
                        help="absolute tolerance for a claim to count as confirmed")
    args = parser.parse_args()

    rows = load(args.csv)
    results: list[tuple[str, str, float, float, bool]] = []  # claim, actual, expected

    def claim(label: str, actual: float, expected: float, tol: float | None = None) -> None:
        # tol=None uses the CLI tolerance; rate claims quoted to one decimal in the
        # draft pass tol=0.05 so rounding is not reported as a factual error.
        limit = args.tolerance if tol is None else tol
        ok = abs(actual - expected) <= limit
        results.append((label, f"{actual:,.4f}", f"{expected:,.4f}", ok))

    col = lambda name: [r[name] for r in rows]  # noqa: E731
    target = col(TARGET)
    class0 = [r for r in rows if r[TARGET] == 0]
    class1 = [r for r in rows if r[TARGET] == 1]

    print("=" * 78)
    print("DRAFT CLAIM VERIFICATION — Table 8 descriptive statistics")
    print("=" * 78)
    claim("LIMIT_BAL mean", mean(col("LIMIT_BAL")), 167484.32)
    claim("LIMIT_BAL std", stdev(col("LIMIT_BAL")), 129747.66)
    claim("LIMIT_BAL p25", quantile(col("LIMIT_BAL"), .25), 50000.00)
    claim("LIMIT_BAL median", quantile(col("LIMIT_BAL"), .50), 140000.00)
    claim("AGE mean", mean(col("AGE")), 35.49)
    claim("AGE std", stdev(col("AGE")), 9.22)
    claim("AGE p25", quantile(col("AGE"), .25), 28.00)
    claim("AGE median", quantile(col("AGE"), .50), 34.00)
    claim("PAY_0 mean", mean(col("PAY_0")), -0.02)
    claim("PAY_0 std", stdev(col("PAY_0")), 1.12)
    claim("BILL_AMT1 mean", mean(col("BILL_AMT1")), 51223.33)
    claim("BILL_AMT1 std", stdev(col("BILL_AMT1")), 73635.86)
    claim("BILL_AMT1 p25", quantile(col("BILL_AMT1"), .25), 3558.75)
    claim("BILL_AMT1 median", quantile(col("BILL_AMT1"), .50), 22381.50)
    claim("BILL_AMT2 mean", mean(col("BILL_AMT2")), 49179.08)
    claim("BILL_AMT2 std", stdev(col("BILL_AMT2")), 71173.77)
    claim("BILL_AMT2 p25", quantile(col("BILL_AMT2"), .25), 2984.75)
    claim("BILL_AMT2 median", quantile(col("BILL_AMT2"), .50), 21200.00)
    claim("PAY_AMT1 mean", mean(col("PAY_AMT1")), 5663.58)
    claim("PAY_AMT1 std", stdev(col("PAY_AMT1")), 16563.28)
    claim("PAY_AMT1 p25", quantile(col("PAY_AMT1"), .25), 1000.00)
    claim("PAY_AMT1 median", quantile(col("PAY_AMT1"), .50), 2100.00)
    claim("PAY_AMT2 mean", mean(col("PAY_AMT2")), 5921.16)
    claim("PAY_AMT2 std", stdev(col("PAY_AMT2")), 23040.87)
    claim("PAY_AMT2 p25", quantile(col("PAY_AMT2"), .25), 833.00)
    claim("PAY_AMT2 median", quantile(col("PAY_AMT2"), .50), 2009.00)

    print()
    print("=" * 78)
    print("DRAFT CLAIM VERIFICATION — §3 EDA statements")
    print("=" * 78)
    claim("class 0 share %", 100 * len(class0) / len(rows), 77.88, tol=0.05)
    claim("class 1 share %", 100 * len(class1) / len(rows), 22.12, tol=0.05)
    claim("LIMIT_BAL mean | class 0", mean([r["LIMIT_BAL"] for r in class0]), 178099.73)
    claim("LIMIT_BAL mean | class 1", mean([r["LIMIT_BAL"] for r in class1]), 130109.66)
    claim("LIMIT_BAL median | class 0", quantile([r["LIMIT_BAL"] for r in class0], .50), 150000.00)
    claim("LIMIT_BAL median | class 1", quantile([r["LIMIT_BAL"] for r in class1], .50), 90000.00)

    # §3.4 default rate by PAY_0 code
    by_pay0: dict[int, list[float]] = defaultdict(list)
    for r in rows:
        by_pay0[int(r["PAY_0"])].append(r[TARGET])
    expected_pay0 = {-2: 13.2, -1: 16.8, 0: 12.8, 1: 33.9, 2: 69.1, 3: 75.8}
    print()
    print("PAY_0 code | n      | default rate % | draft claim %")
    for code in sorted(by_pay0):
        vals = by_pay0[code]
        rate = 100 * sum(vals) / len(vals)
        claim(f"default rate PAY_0={code}", rate, expected_pay0[code], tol=0.05) if code in expected_pay0 else None
        draft = f"{expected_pay0[code]:.1f}" if code in expected_pay0 else "-"
        print(f"  {code:>3}      | {len(vals):<6} | {rate:>13.1f} | {draft:>13}")

    # §3.5 default rate by EDUCATION (draft: 1=19.2, 2=23.7, 3=25.2, others=5.7)
    by_edu: dict[int, list[float]] = defaultdict(list)
    for r in rows:
        by_edu[int(r["EDUCATION"])].append(r[TARGET])
    expected_edu = {1: 19.2, 2: 23.7, 3: 25.2}
    others = [r[TARGET] for r in rows if int(r["EDUCATION"]) not in (1, 2, 3)]
    print()
    print("EDUCATION | n      | default rate % | draft claim %")
    for code in sorted(by_edu):
        vals = by_edu[code]
        rate = 100 * sum(vals) / len(vals)
        if code in expected_edu:
            claim(f"default rate EDUCATION={code}", rate, expected_edu[code], tol=0.05)
        draft = f"{expected_edu[code]:.1f}" if code in expected_edu else "-"
        print(f"  {code:>7} | {len(vals):<6} | {rate:>13.1f} | {draft:>13}")
    others_rate = 100 * sum(others) / len(others)
    claim("default rate EDUCATION in 0,4,5,6 (draft 'others' 5.7)", others_rate, 5.7)
    claim("default rate EDUCATION=4 only (source of draft 5.7)", 100 * sum(by_edu[4]) / len(by_edu[4]), 5.7, tol=0.05)
    print(f"  others    | {len(others):<6} | {others_rate:>13.1f} | {5.7:>13.1f}")

    # §3.6 correlations
    claim("corr(PAY_0, target)", pearson(col("PAY_0"), target), 0.32, tol=0.005)
    claim("corr(PAY_2, target)", pearson(col("PAY_2"), target), 0.26, tol=0.005)
    claim("corr(PAY_3, target)", pearson(col("PAY_3"), target), 0.24, tol=0.005)
    claim("corr(LIMIT_BAL, target)", pearson(col("LIMIT_BAL"), target), -0.15, tol=0.005)
    claim("corr(BILL_AMT1, BILL_AMT2)", pearson(col("BILL_AMT1"), col("BILL_AMT2")), 0.95, tol=0.005)

    # §4.1 stratified 80/20 split composition
    claim("stratified test class 0 (expect 4673)", round(0.2 * len(class0)), 4673)
    claim("stratified test class 1 (expect 1327)", round(0.2 * len(class1)), 1327)

    # §4.2 Table 9: recompute every metric from the published confusion-matrix
    # counts. No artifact exists yet, so this checks internal consistency and
    # agreement with the dataset's class balance -- not that the model was trained.
    print()
    print("=" * 78)
    print("DRAFT CLAIM VERIFICATION — Table 9 confusion-matrix arithmetic")
    print("=" * 78)
    table9 = {
        "Logistic Regression": (4528, 145, 1009, 318, 0.8077, 0.6868, 0.2396, 0.3553),
        "Decision Tree": (4432, 241, 856, 471, 0.8172, 0.6615, 0.3549, 0.4620),
        "Random Forest": (4491, 182, 945, 382, 0.8122, 0.6773, 0.2879, 0.4040),
    }
    print(f"  {'model':<20} {'n':>5} {'acc':>7} {'prec':>7} {'rec':>7} {'f1':>7} "
          f"{'class1':>7} {'class0':>7}")
    for name, (tn, fp, fn, tp, acc, prec, rec, f1) in table9.items():
        n = tn + fp + fn + tp
        calc_acc = (tn + tp) / n
        calc_prec = tp / (tp + fp)
        calc_rec = tp / (tp + fn)
        calc_f1 = 2 * calc_prec * calc_rec / (calc_prec + calc_rec)
        print(f"  {name:<20} {n:>5} {calc_acc:>7.4f} {calc_prec:>7.4f} "
              f"{calc_rec:>7.4f} {calc_f1:>7.4f} {tp + fn:>7} {tn + fp:>7}")
        claim(f"Table9 {name} n", n, 6000)
        claim(f"Table9 {name} accuracy", round(calc_acc, 4), acc, tol=0.00005)
        claim(f"Table9 {name} precision", round(calc_prec, 4), prec, tol=0.00005)
        claim(f"Table9 {name} recall", round(calc_rec, 4), rec, tol=0.00005)
        claim(f"Table9 {name} f1", round(calc_f1, 4), f1, tol=0.00005)
        # every model must see the same stratified test set
        claim(f"Table9 {name} test defaults (20% of 6636)", tp + fn, 1327)

    print()
    print("=" * 78)
    print("RESULTS")
    print("=" * 78)
    failed = [r for r in results if not r[3]]
    for label, actual, expected, ok in results:
        print(f"  [{'CONFIRMED' if ok else 'MISMATCH '}] {label:<40} actual={actual:>14}  draft={expected:>14}")
    print()
    print(f"confirmed: {len(results) - len(failed)}/{len(results)}")
    if failed:
        print("MISMATCHES:")
        for label, actual, expected, _ in failed:
            print(f"  - {label}: actual={actual} draft={expected}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
