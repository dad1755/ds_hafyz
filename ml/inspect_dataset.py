#!/usr/bin/env python3
"""Dataset integrity inspection for UCI_Credit_Card.csv (Sprint 0 / S2).

Standard library only, so it runs before the ML environment exists and can be
re-run in CI without pandas. Prints a deterministic report to stdout and exits
non-zero when the CSV disagrees with the documented contract.

Usage:
    python3 ml/inspect_dataset.py --csv data/UCI_Credit_Card.csv
    python3 ml/inspect_dataset.py --csv data/UCI_Credit_Card.csv \
        --expect-rows 30000 --expect-cols 25 --json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

TARGET = "default.payment.next.month"
ID_COLUMN = "ID"

# Ordered column contract (blueprint §4). Kept here so the inspection can fail
# loudly if the supplied file ever drifts from the documented schema.
EXPECTED_COLUMNS = [
    "ID",
    "LIMIT_BAL",
    "SEX",
    "EDUCATION",
    "MARRIAGE",
    "AGE",
    "PAY_0",
    "PAY_2",
    "PAY_3",
    "PAY_4",
    "PAY_5",
    "PAY_6",
    "BILL_AMT1",
    "BILL_AMT2",
    "BILL_AMT3",
    "BILL_AMT4",
    "BILL_AMT5",
    "BILL_AMT6",
    "PAY_AMT1",
    "PAY_AMT2",
    "PAY_AMT3",
    "PAY_AMT4",
    "PAY_AMT5",
    "PAY_AMT6",
    "default.payment.next.month",
]

# Documented facts this sprint must verify by code (blueprint §0 / §9 S0).
EXPECTED_ROWS = 30_000
EXPECTED_COLS = 25
EXPECTED_MISSING = 0
EXPECTED_DUPES = 0
EXPECTED_CLASS_0 = 23_364
EXPECTED_CLASS_1 = 6_636
EXPECTED_SHA256 = "a0f0ab49d6326671d6cd83be5c88dcf18007025fe9a53ecd699119c871176ca1"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_int(text: str) -> bool:
    try:
        int(text)
        return True
    except ValueError:
        return False


def is_float(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def infer_dtype(values: list[str], blanks: int) -> str:
    """Narrowest numpy-style dtype that fits every non-blank value."""
    if blanks == len(values):
        return "object"
    non_blank = [v for v in values if v != ""]
    if all(is_int(v) for v in non_blank):
        return "int64"
    if all(is_float(v) for v in non_blank):
        return "float64"
    return "object"


def inspect(path: Path) -> dict:
    report: dict = {"csv": str(path), "sha256": sha256_of(path), "size_bytes": path.stat().st_size}

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header is None:
            raise SystemExit("ERROR: empty CSV (no header row)")
        report["columns"] = header
        report["column_count"] = len(header)

        columns: list[list[str]] = [[] for _ in header]
        sci_notation: list[int] = [0 for _ in header]
        fractional: list[int] = [0 for _ in header]
        row_count = 0
        ragged = 0
        row_hashes: Counter[str] = Counter()
        target_counts: Counter[str] = Counter()

        for row in reader:
            if not row or all(cell.strip() == "" for cell in row):
                continue  # trailing blank line, not a record
            row_count += 1
            if len(row) != len(header):
                ragged += 1
                continue
            for index, cell in enumerate(row):
                cell = cell.strip()
                columns[index].append(cell)
                # Excel round-trips write large amounts as 5e+05; record it rather
                # than letting a naive int() parse silently reclassify the dtype.
                if "e" in cell.lower():
                    sci_notation[index] += 1
                if is_float(cell) and float(cell) != int(float(cell)):
                    fractional[index] += 1
            row_hashes["\x1f".join(row)] += 1
            if TARGET in header:
                target_counts[row[header.index(TARGET)].strip()] += 1

    report["row_count"] = row_count
    report["ragged_rows"] = ragged
    report["duplicate_full_rows"] = sum(count - 1 for count in row_hashes.values() if count > 1)
    report["duplicate_row_groups"] = sum(1 for count in row_hashes.values() if count > 1)

    per_column = []
    total_missing = 0
    for position, (name, values) in enumerate(zip(header, columns)):
        blanks = sum(1 for v in values if v == "")
        total_missing += blanks
        numeric = [float(v) for v in values if v != "" and is_float(v)]
        per_column.append(
            {
                "column": name,
                "dtype": infer_dtype(values, blanks),
                "missing": blanks,
                "unique": len(set(values)),
                "min": min(numeric) if numeric else None,
                "max": max(numeric) if numeric else None,
                "sci_notation_cells": sci_notation[position],
                "fractional_cells": fractional[position],
            }
        )
    report["missing_cells"] = total_missing
    report["per_column"] = per_column

    report["target_column"] = TARGET
    report["target_counts"] = dict(target_counts)
    total_target = sum(target_counts.values())
    report["target_pct"] = {
        key: round(100.0 * value / total_target, 2) for key, value in target_counts.items()
    } if total_target else {}

    report["sci_notation_cells"] = sum(sci_notation)
    report["sci_notation_by_column"] = {
        name: count for name, count in zip(header, sci_notation) if count
    }
    report["fractional_cells"] = sum(fractional)

    features = [c for c in header if c not in (ID_COLUMN, TARGET)]
    report["predictor_count"] = len(features)
    report["predictors"] = features

    # Contract checks
    checks = []
    def check(label: str, actual, expected) -> None:
        checks.append({"check": label, "actual": actual, "expected": expected, "pass": actual == expected})

    check("sha256", report["sha256"], EXPECTED_SHA256)
    check("row_count", row_count, EXPECTED_ROWS)
    check("column_count", len(header), EXPECTED_COLS)
    check("ordered_columns", header, EXPECTED_COLUMNS)
    check("missing_cells", total_missing, EXPECTED_MISSING)
    check("duplicate_full_rows", report["duplicate_full_rows"], EXPECTED_DUPES)
    check("ragged_rows", ragged, 0)
    check("predictor_count", len(features), 23)
    check("class_0", target_counts.get("0", 0), EXPECTED_CLASS_0)
    check("class_1", target_counts.get("1", 0), EXPECTED_CLASS_1)
    check("target_total_equals_rows", total_target, row_count)
    # Monetary columns are whole NTD in this source; a fractional value would mean
    # the export mangled precision and the dataset must not be trusted as-is.
    check("fractional_values_in_monetary_columns", sum(fractional), 0)
    report["checks"] = checks
    report["all_checks_pass"] = all(c["pass"] for c in checks)
    return report


def print_report(report: dict) -> None:
    print("=" * 78)
    print("DATASET INSPECTION — UCI_Credit_Card.csv")
    print("=" * 78)
    print(f"path        : {report['csv']}")
    print(f"size_bytes  : {report['size_bytes']}")
    print(f"sha256      : {report['sha256']}")
    print(f"rows        : {report['row_count']}")
    print(f"columns     : {report['column_count']}")
    print(f"predictors  : {report['predictor_count']} (excluding ID and target)")
    print(f"missing     : {report['missing_cells']} cells")
    print(f"dupes       : {report['duplicate_full_rows']} duplicated full rows "
          f"({report['duplicate_row_groups']} groups)")
    print(f"ragged rows : {report['ragged_rows']}")
    print(f"sci-notation: {report['sci_notation_cells']} numeric cells written as 5e+05 "
          f"(all parse to whole numbers; {report['fractional_cells']} fractional values)")
    if report["sci_notation_by_column"]:
        for name, count in report["sci_notation_by_column"].items():
            print(f"              - {name}: {count}")
    print()
    print("ORDERED COLUMNS")
    for index, name in enumerate(report["columns"]):
        print(f"  {index:2d}. {name}")
    print()
    print("DTYPES / MISSING / RANGE")
    print(f"  {'column':<30} {'dtype':<8} {'missing':>7} {'unique':>7} {'min':>12} {'max':>12}")
    for row in report["per_column"]:
        def fmt(value):
            if value is None:
                return "-"
            return f"{value:.0f}" if float(value).is_integer() else f"{value}"
        print(f"  {row['column']:<30} {row['dtype']:<8} {row['missing']:>7} "
              f"{row['unique']:>7} {fmt(row['min']):>12} {fmt(row['max']):>12}")
    print()
    print("TARGET DISTRIBUTION — default.payment.next.month")
    for key in sorted(report["target_counts"]):
        label = "no default next month" if key == "0" else "default next month"
        print(f"  class {key} ({label}): {report['target_counts'][key]} "
              f"({report['target_pct'].get(key, 0.0)}%)")
    print()
    print("CONTRACT CHECKS")
    for item in report["checks"]:
        status = "PASS" if item["pass"] else "FAIL"
        detail = "" if item["pass"] else f"  actual={item['actual']!r} expected={item['expected']!r}"
        print(f"  [{status}] {item['check']}{detail}")
    print()
    print(f"RESULT: {'ALL CHECKS PASS' if report['all_checks_pass'] else 'CHECKS FAILED'}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default="data/UCI_Credit_Card.csv")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of text")
    parser.add_argument("--out", help="also write the report to this path")
    args = parser.parse_args(argv)

    path = Path(args.csv)
    if not path.is_file():
        print(f"ERROR: no such file: {path}", file=sys.stderr)
        return 2

    report = inspect(path)
    if args.json:
        text = json.dumps(report, indent=2)
        print(text)
    else:
        print_report(report)
        text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    return 0 if report["all_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
