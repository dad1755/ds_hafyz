#!/usr/bin/env python3
"""Write the CSV the S13 browser check uploads through the dataset manager.

A prefix of the seed dataset — same 25-column header and order, different bytes, so the upload
is a genuinely new dataset version rather than a duplicate of the seed (the manager rejects
identical bytes by checksum and that rejection is a different test).

    python3 evidence/s13/make_upload_subset.py /path/out.csv [rows]
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

rows = int(sys.argv[2]) if len(sys.argv) > 2 else 500
out = Path(sys.argv[1])
seed = Path(__file__).resolve().parent.parent.parent / "data" / "UCI_Credit_Card.csv"

with seed.open(newline="", encoding="utf-8") as source, out.open("w", newline="", encoding="utf-8") as sink:
    reader = csv.reader(source)
    writer = csv.writer(sink)
    writer.writerow(next(reader))
    for index, row in enumerate(reader):
        if index >= rows:
            break
        writer.writerow(row)

print(f"wrote {out.name}: {rows} data rows + header, {out.stat().st_size} bytes")
