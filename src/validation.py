"""Dataset and model-input validation (blueprint §4; Sprint 2).

Three entry points:

``validate_csv_bytes(payload)``
    Validate a whole uploaded CSV against the 25-column contract. Returns a
    :class:`ValidationReport` carrying *every* problem found, so an admin upload screen
    can list them all at once. Nothing is written and nothing is cleaned.

``validate_dataframe(frame)``
    The same value checks for an already-parsed frame (used by tests and by the
    dataset manager when a file arrives through another route).

``validate_features(record)``
    Validate one 23-feature prediction request (the UI form, later the prediction
    service). Raises :class:`ValidationError` on the first problem.

Error discipline: every failure carries a stable machine ``code`` and a message that
names the column and how many rows offend. Messages never echo a cell value, a row's
contents or a filename — an upload error is rendered back to an admin, and the dataset
contains customer records.

Nothing here mutates the supplied bytes, the frame, or ``data/UCI_Credit_Card.csv``.
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from ml.schema import (
    COLUMNS,
    COLUMN_SPECS,
    FEATURE_SPECS,
    FEATURES,
    ID_COLUMN,
    TARGET_COLUMN,
    dataset_metadata,
    metadata_checksum,
)

#: Hard ceiling for an uploaded dataset (10 MB). The supplied seed is 2.86 MB, so this
#: leaves room for a superset without letting a request body exhaust the container.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

#: Where unvalidated uploads are parked. Git-ignored; never the seed directory.
DEFAULT_QUARANTINE_DIR = Path("data/quarantine")

#: Every code this module can emit, with the meaning an operator needs. Codes are part
#: of the API: tests assert them and the admin screen renders them.
ERROR_CODES: dict[str, str] = {
    "empty_file": "the upload contained no bytes",
    "file_too_large": f"the upload exceeds the {MAX_UPLOAD_BYTES} byte limit",
    "not_utf8": "the upload is not UTF-8 text",
    "malformed_csv": "the CSV cannot be parsed (for example a row with the wrong field count)",
    "duplicate_column": "the header repeats a column name",
    "missing_column": "a required column is absent",
    "extra_column": "the header carries a column outside the contract",
    "column_order": "the columns are present but not in the documented order",
    "empty_data": "the file has a header but no data rows",
    "missing_value": "a cell is empty or NaN",
    "not_numeric": "a cell in a numeric column is not a number",
    "non_finite": "a cell is infinite",
    "non_integer": "a cell in an integer column has a fractional part",
    "unsupported_code": "a coded column carries a value outside its documented code set",
    "invalid_target_value": "the target column carries a value other than 0 or 1",
    "out_of_range": "a value falls outside its documented validation range",
    "missing_feature": "a required feature is absent from the request",
    "unknown_feature": "the request carries a key that is not one of the 23 features",
    "not_a_mapping": "the request is not a mapping of feature name to value",
}


class ValidationError(Exception):
    """A single, actionable validation failure.

    ``code`` is stable and machine-readable, ``message`` is safe to show a user, and
    ``column`` / ``rows`` narrow the problem without exposing any cell content.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        column: str | None = None,
        rows: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.column = column
        self.rows = rows

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "column": self.column, "rows": self.rows, "message": self.message}

    def __str__(self) -> str:  # pragma: no cover - convenience for logs
        return f"[{self.code}] {self.message}"


@dataclass
class ValidationReport:
    """Outcome of validating a whole dataset.

    ``ok`` is true only when ``errors`` is empty. The metadata fields are filled from
    the file itself and are what a ``dataset_versions`` row records.
    """

    ok: bool = False
    errors: list[ValidationError] = field(default_factory=list)
    sha256: str | None = None
    size_bytes: int = 0
    record_count: int = 0
    column_count: int = 0
    class_zero: int = 0
    class_one: int = 0
    metadata_checksum: str | None = None

    @property
    def codes(self) -> set[str]:
        """The set of error codes found — the assertion surface for tests."""
        return {error.code for error in self.errors}

    def messages(self) -> list[str]:
        return [error.message for error in self.errors]

    def fail(self, code: str, message: str, *, column: str | None = None, rows: int | None = None) -> None:
        self.errors.append(ValidationError(code, message, column=column, rows=rows))
        self.ok = False

    def require_valid(self) -> None:
        """Raise the first error; a no-op when the report is clean."""
        if self.errors:
            raise self.errors[0]

    def metadata(self) -> dict[str, Any] | None:
        """The ``dataset_versions`` metadata for a clean report, else ``None``."""
        if not self.ok or self.sha256 is None:
            return None
        return dataset_metadata(
            sha256=self.sha256,
            record_count=self.record_count,
            column_count=self.column_count,
            class_zero=self.class_zero,
            class_one=self.class_one,
        )


# --------------------------------------------------------------------------- helpers
def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _header_of(text: str) -> list[str]:
    """First non-blank row of the CSV, with surrounding whitespace removed."""
    for row in csv.reader(io.StringIO(text)):
        if row and any(cell.strip() for cell in row):
            return [cell.strip() for cell in row]
    return []


def _check_header(header: Sequence[str], report: ValidationReport) -> bool:
    """Structural header checks. Returns ``False`` when the header is unusable."""
    if not header:
        report.fail("empty_data", "the file has no header row; expected the 25 documented columns")
        return False

    seen: dict[str, int] = {}
    for name in header:
        seen[name] = seen.get(name, 0) + 1
    duplicates = sorted(name for name, count in seen.items() if count > 1)
    if duplicates:
        report.fail(
            "duplicate_column",
            "the header repeats column name(s) "
            + ", ".join(repr(name) for name in duplicates)
            + "; each of the 25 contract columns may appear exactly once",
        )
        return False

    present = set(header)
    missing = [name for name in COLUMNS if name not in present]
    if missing:
        report.fail(
            "missing_column",
            f"missing required column(s): {', '.join(missing)}; "
            f"the file must contain all {len(COLUMNS)} documented columns "
            "(see docs/data_dictionary.md)",
        )
        return False

    extra = [name for name in header if name not in set(COLUMNS)]
    if extra:
        report.fail(
            "extra_column",
            f"unexpected column(s): {', '.join(extra)}; "
            f"the contract has exactly {len(COLUMNS)} columns and does not accept extras",
        )
        return False

    if list(header) != list(COLUMNS):
        first = next(
            index for index, (actual, expected) in enumerate(zip(header, COLUMNS)) if actual != expected
        )
        report.fail(
            "column_order",
            f"column {first + 1} is {header[first]!r} but the contract requires "
            f"{COLUMNS[first]!r}; the 25 columns must appear in the documented order",
            column=header[first],
        )
        return False
    return True


def _check_values(frame: pd.DataFrame, report: ValidationReport) -> None:
    """Per-column value checks. Appends every problem found; never raises."""
    for spec in COLUMN_SPECS:
        if spec.kind == "id" or spec.name not in frame.columns:
            continue
        series = frame[spec.name]
        nulls = series.isna()
        numeric = pd.to_numeric(series, errors="coerce")

        if nulls.any():
            report.fail(
                "missing_value",
                f"column {spec.name!r} has {int(nulls.sum())} empty or NaN cell(s); "
                "the dataset must be complete",
                column=spec.name,
                rows=int(nulls.sum()),
            )

        non_null = ~nulls
        unparsed = non_null & numeric.isna()
        if unparsed.any():
            report.fail(
                "not_numeric",
                f"column {spec.name!r} has {int(unparsed.sum())} non-numeric cell(s); "
                f"it must hold whole numbers in {spec.unit}",
                column=spec.name,
                rows=int(unparsed.sum()),
            )

        infinite = np.isinf(numeric)
        if bool(infinite.any()):
            report.fail(
                "non_finite",
                f"column {spec.name!r} has {int(infinite.sum())} infinite cell(s); "
                "non-finite values cannot be modelled",
                column=spec.name,
                rows=int(infinite.sum()),
            )

        comparable = numeric[non_null & ~unparsed & ~infinite]
        fractional = comparable.notna() & (comparable % 1 != 0)
        if fractional.any():
            report.fail(
                "non_integer",
                f"column {spec.name!r} has {int(fractional.sum())} cell(s) with a fractional "
                f"part; it must hold whole numbers in {spec.unit}",
                column=spec.name,
                rows=int(fractional.sum()),
            )

        if spec.allowed is not None:
            allowed = pd.Series(sorted(spec.allowed), dtype="float64")
            invalid = comparable.notna() & ~comparable.isin(allowed)
            if invalid.any():
                code = "invalid_target_value" if spec.kind == "target" else "unsupported_code"
                if spec.kind == "target":
                    message = (
                        f"column {spec.name!r} has {int(invalid.sum())} value(s) other than 0 or 1; "
                        "1 means default on next month's payment, 0 means no default"
                    )
                else:
                    message = (
                        f"column {spec.name!r} has {int(invalid.sum())} value(s) outside its "
                        f"documented code set {sorted(spec.allowed)}"
                    )
                report.fail(code, message, column=spec.name, rows=int(invalid.sum()))

        if spec.minimum is not None:
            below = comparable.notna() & (comparable < spec.minimum)
            if below.any():
                report.fail(
                    "out_of_range",
                    f"column {spec.name!r} has {int(below.sum())} value(s) below the "
                    f"documented minimum {spec.minimum} {spec.unit}",
                    column=spec.name,
                    rows=int(below.sum()),
                )
        if spec.maximum is not None:
            above = comparable.notna() & (comparable > spec.maximum)
            if above.any():
                report.fail(
                    "out_of_range",
                    f"column {spec.name!r} has {int(above.sum())} value(s) above the "
                    f"documented maximum {spec.maximum} {spec.unit}",
                    column=spec.name,
                    rows=int(above.sum()),
                )


def _finish(report: ValidationReport, frame: pd.DataFrame, payload: bytes) -> ValidationReport:
    """Fill the metadata fields from a validated frame."""
    report.sha256 = _sha256(payload)
    report.size_bytes = len(payload)
    report.record_count = int(len(frame))
    report.column_count = int(len(frame.columns))
    target = pd.to_numeric(frame[TARGET_COLUMN], errors="coerce")
    report.class_zero = int((target == 0).sum())
    report.class_one = int((target == 1).sum())
    report.metadata_checksum = metadata_checksum(
        dataset_metadata(
            sha256=report.sha256,
            record_count=report.record_count,
            column_count=report.column_count,
            class_zero=report.class_zero,
            class_one=report.class_one,
        )
    )
    report.ok = not report.errors
    return report


# --------------------------------------------------------------------------- CSV
def validate_csv_bytes(
    payload: bytes,
    *,
    filename: str | None = None,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> ValidationReport:
    """Validate a complete CSV payload against the 25-column contract.

    ``filename`` is accepted only so a caller can correlate the report with its upload;
    it is never parsed, stored or echoed in a message.
    """
    del filename  # deliberately unused: no uploaded name reaches a path or a message
    report = ValidationReport()

    if not payload:
        report.fail("empty_file", "the upload is empty; nothing was read")
        return report
    if len(payload) > max_bytes:
        report.fail(
            "file_too_large",
            f"the upload is {len(payload)} bytes, above the {max_bytes} byte limit; "
            "upload a smaller CSV",
        )
        report.size_bytes = len(payload)
        return report

    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        report.fail("not_utf8", "the upload is not valid UTF-8 text; save it as UTF-8 CSV")
        return report

    if not _check_header(_header_of(text), report):
        return report

    try:
        frame = pd.read_csv(io.BytesIO(payload), encoding="utf-8-sig")
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError):
        report.fail(
            "malformed_csv",
            "the CSV cannot be parsed; check that every row has the same number of fields "
            "as the header",
        )
        return report

    if len(frame) == 0:
        report.fail("empty_data", "the file has a header but no data rows")
        return report

    _check_values(frame, report)
    return _finish(report, frame, payload)


def validate_dataframe(frame: pd.DataFrame) -> ValidationReport:
    """Validate an already-parsed frame against the same contract."""
    report = ValidationReport()
    if len(frame) == 0:
        report.fail("empty_data", "the dataset has no rows")
        return report
    if not _check_header([str(name) for name in frame.columns], report):
        return report

    _check_values(frame, report)
    payload = frame.to_csv(index=False).encode("utf-8")
    return _finish(report, frame, payload)


# --------------------------------------------------------------------------- single record
def _coerce_number(raw: Any, name: str) -> float:
    if isinstance(raw, bool):
        raise ValidationError(
            "not_numeric", f"feature {name!r} received a boolean; it must be a whole number"
        )
    if raw is None:
        raise ValidationError("missing_value", f"feature {name!r} has no value")
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ValidationError("missing_value", f"feature {name!r} is an empty string")
        try:
            return float(text)
        except ValueError:
            raise ValidationError(
                "not_numeric", f"feature {name!r} is not a number"
            ) from None
    if isinstance(raw, (int, float, np.integer, np.floating)):
        return float(raw)
    raise ValidationError("not_numeric", f"feature {name!r} is not a number")


def validate_features(record: Mapping[str, Any]) -> dict[str, int]:
    """Validate one 23-feature request and return it in contract order.

    Raises :class:`ValidationError` on the first problem. Values are accepted as whole
    numbers or as their string form (a form field arrives as text); booleans are not
    numbers here.
    """
    if not isinstance(record, Mapping):
        raise ValidationError(
            "not_a_mapping", "the prediction request must map feature names to values"
        )

    missing = [name for name in FEATURES if name not in record]
    if missing:
        raise ValidationError(
            "missing_feature",
            f"missing feature(s): {', '.join(missing)}; all {len(FEATURES)} features are required",
        )
    unknown = sorted(str(key) for key in record if key not in FEATURES)
    if unknown:
        raise ValidationError(
            "unknown_feature",
            f"unexpected key(s): {', '.join(unknown)}; the model takes exactly the "
            f"{len(FEATURES)} documented features",
        )

    validated: dict[str, int] = {}
    for spec in FEATURE_SPECS:
        value = _coerce_number(record[spec.name], spec.name)
        if not np.isfinite(value):
            raise ValidationError(
                "non_finite",
                f"feature {spec.name!r} is not a finite number; enter a real value",
                column=spec.name,
            )
        if value != int(value):
            raise ValidationError(
                "non_integer",
                f"feature {spec.name!r} must be a whole number in {spec.unit}",
                column=spec.name,
            )
        integer = int(value)
        if spec.allowed is not None and integer not in spec.allowed:
            raise ValidationError(
                "unsupported_code",
                f"feature {spec.name!r} has code {integer}, outside the documented set "
                f"{sorted(spec.allowed)}",
                column=spec.name,
            )
        low, high = spec.form or (spec.minimum, spec.maximum)
        if low is not None and integer < low:
            raise ValidationError(
                "out_of_range",
                f"feature {spec.name!r} must be at least {low} {spec.unit}",
                column=spec.name,
            )
        if high is not None and integer > high:
            raise ValidationError(
                "out_of_range",
                f"feature {spec.name!r} must be at most {high} {spec.unit}",
                column=spec.name,
            )
        validated[spec.name] = integer
    return validated


# --------------------------------------------------------------------------- quarantine
@dataclass(frozen=True)
class QuarantinedUpload:
    """An upload parked under a generated name, with the checksum of its bytes."""

    path: Path
    generated_filename: str
    original_filename_safe: str
    sha256: str
    size_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "generated_filename": self.generated_filename,
            "original_filename_safe": self.original_filename_safe,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


def sanitize_filename(original: str | None, *, limit: int = 120) -> str:
    """Reduce an uploaded name to a display-only label.

    Only the final path component survives, control characters and separators are
    dropped, a leading dot is removed and a ``.csv`` suffix is enforced. The result is
    stored for the admin's benefit in ``dataset_versions.original_filename_safe`` and is
    never used to build a path.
    """
    raw = str(original or "").replace("\\", "/")
    base = os.path.basename(raw)
    base = "".join(ch for ch in base if ch.isprintable() and ch not in '/\\:*?"<>|')
    base = base.strip().lstrip(".")
    if not base:
        base = "upload.csv"
    if not base.lower().endswith(".csv"):
        base = f"{base}.csv"
    return base[:limit]


def quarantine_upload(
    payload: bytes,
    original_filename: str | None = None,
    *,
    quarantine_dir: Path | str = DEFAULT_QUARANTINE_DIR,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> QuarantinedUpload:
    """Write ``payload`` to a controlled quarantine path and return its identity.

    The stored name is generated (UTC timestamp + random token + ``.csv``) so the
    uploaded name cannot influence the path at all; the resolved path is then asserted
    to sit directly inside ``quarantine_dir``. The write is exclusive and does not
    follow symlinks, so an existing file or a planted link can never be overwritten.
    """
    if not payload:
        raise ValidationError("empty_file", "the upload is empty; nothing was quarantined")
    if len(payload) > max_bytes:
        raise ValidationError(
            "file_too_large",
            f"the upload is {len(payload)} bytes, above the {max_bytes} byte limit",
        )

    directory = Path(quarantine_dir)
    directory.mkdir(parents=True, exist_ok=True)
    resolved_dir = directory.resolve()

    for _ in range(2):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        generated = f"{stamp}-{uuid.uuid4().hex[:12]}.csv"
        path = directory / generated
        if path.resolve().parent != resolved_dir:
            raise RuntimeError("quarantine path escaped its directory")  # pragma: no cover
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:  # pragma: no cover - a 48-bit token collision
            continue
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
        except BaseException:  # pragma: no cover - never leave a partial file behind
            path.unlink(missing_ok=True)
            raise
        return QuarantinedUpload(
            path=path,
            generated_filename=generated,
            original_filename_safe=sanitize_filename(original_filename),
            sha256=_sha256(payload),
            size_bytes=len(payload),
        )
    raise RuntimeError("could not allocate a quarantine filename")  # pragma: no cover


def ingest_upload(
    payload: bytes,
    original_filename: str | None = None,
    *,
    quarantine_dir: Path | str = DEFAULT_QUARANTINE_DIR,
    max_bytes: int = MAX_UPLOAD_BYTES,
) -> tuple[QuarantinedUpload, ValidationReport]:
    """Quarantine an upload, then validate the stored bytes.

    The order is deliberate: the file is parked under a controlled name *before* it is
    parsed, so an invalid file is retained for diagnosis and can never be mistaken for
    the seed. An invalid report leaves the quarantined copy in place for the caller to
    delete once it has been recorded.
    """
    quarantined = quarantine_upload(
        payload, original_filename, quarantine_dir=quarantine_dir, max_bytes=max_bytes
    )
    report = validate_csv_bytes(payload, filename=quarantined.original_filename_safe, max_bytes=max_bytes)
    return quarantined, report
