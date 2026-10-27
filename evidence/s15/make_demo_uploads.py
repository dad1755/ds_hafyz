#!/usr/bin/env python3
"""Write the two CSVs the S15 demo rehearsal uploads through the dataset manager.

Both are built from the seed dataset, so neither is a hand-written fixture:

* ``rehearsal_valid_subset.csv`` — the first 300 data rows, same 25-column header and order.
  Different bytes from the seed and from the 500-row version an earlier run staged, so it is a
  genuinely new dataset version rather than a checksum duplicate.
* ``rehearsal_invalid_missing_column.csv`` — the same rows with the ``PAY_AMT6`` column
  removed. The manager must refuse it with a named reason and record the rejection; nothing is
  repaired, coerced or partially loaded. This is the demo's "dataset validation" step: a
  refusal is a more useful thing to show than a happy path, and it is repeatable.

    python3 evidence/s15/make_demo_uploads.py <out-dir> [rows]
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

rows = int(sys.argv[2]) if len(sys.argv) > 2 else 300
out_dir = Path(sys.argv[1])
out_dir.mkdir(parents=True, exist_ok=True)
seed = Path(__file__).resolve().parents[2] / "data" / "UCI_Credit_Card.csv"

with seed.open(newline="", encoding="utf-8") as source:
    reader = csv.reader(source)
    header = next(reader)
    body = [row for index, row in enumerate(reader) if index < rows]

drop = header.index("PAY_AMT6")
keep = [index for index in range(len(header)) if index != drop]

valid = out_dir / "rehearsal_valid_subset.csv"
with valid.open("w", newline="", encoding="utf-8") as sink:
    writer = csv.writer(sink)
    writer.writerow(header)
    writer.writerows(body)

invalid = out_dir / "rehearsal_invalid_missing_column.csv"
with invalid.open("w", newline="", encoding="utf-8") as sink:
    writer = csv.writer(sink)
    writer.writerow([header[index] for index in keep])
    writer.writerows([[row[index] for index in keep] for row in body])

print(
    f"wrote {valid.name}: {len(body)} data rows + 25-column header, {valid.stat().st_size} bytes"
)
print(
    f"wrote {invalid.name}: {len(body)} data rows + 24-column header "
    f"(PAY_AMT6 removed), {invalid.stat().st_size} bytes"
)
