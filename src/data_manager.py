"""Dataset versions, staging and activation (blueprint §6 ``dataset_versions``; §9 SPRINT 9).

The module answers one question the demo has to answer honestly: **which dataset built the
model that is answering right now?** That is the dataset recorded in
``models/model_manifest.json``, and nothing here can change it. An upload is validated and
recorded as a *staged* dataset version; activating one moves a pointer that a future
*explicit* retraining run would read. No function in this module trains, fits, pickles or
writes into ``models/`` — there is no import of :mod:`ml.train` anywhere, and the audit row
for every upload and activation records ``retraining_triggered: false``.

Invariants enforced here, not merely displayed by the page:

* **Exactly one active version.** Activation runs inside one transaction that clears the old
  pointer and sets the new one; the database also carries a partial unique index on
  ``is_active = 1``, so two writers cannot both win even if this code is bypassed.
* **Only validated data becomes a version.** A rejected upload is written to
  ``dataset_rejections`` with the same reason the admin saw, plus an ``audit_events`` row. Its
  quarantine copy is removed after the record is written; its bytes never become a version.
* **The uploaded filename never builds a path.** Quarantine uses a generated name
  (:func:`src.validation.quarantine_upload`) and the original is stored only as a label.
* **Nothing is cleaned silently.** The validator reports every problem it finds and the upload
  is refused; there is no imputation, row drop or value coercion on the way in.

Every privileged function starts with :func:`src.security.require_role`. The page hides
these operations from non-admins; a direct call with a user session raises
:class:`~src.security.PermissionDenied` and is audited.
"""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ml.schema import COLUMN_SPECS, COLUMNS, TARGET_COLUMN
from src import audit, security, validation
from src.db import to_iso, transaction, utcnow
from src.security import AuthError, PolicyViolation, Principal

#: Longest reason string stored for a rejection. The validator's first message is always
#: included; the cap only bounds how much of a multi-problem report is kept verbatim.
MAX_REASON_CHARS = 600

#: Where the deployed artifact and its manifest live, relative to the app root.
DEFAULT_MODELS_DIR = Path("models")

#: The immutable seed dataset. Preserved untouched (blueprint §4): it is the benchmark's input
#: and the dataset the shipped model was trained on.
DEFAULT_SEED_PATH = Path("data/UCI_Credit_Card.csv")

ARTIFACT_NAME = "best_pipeline.joblib"
MANIFEST_NAME = "model_manifest.json"

#: Statuses a version row can carry. Rejections are not versions — they are in
#: ``dataset_rejections`` — so ``rejected`` never appears here; the UI shows both tables.
STATUS_VALIDATED = "validated"
STATUS_ACTIVATED = "activated"


class DatasetRejected(AuthError):
    """An upload that failed validation. ``report`` carries every problem found."""

    public_message = "The dataset was rejected."

    def __init__(self, report: validation.ValidationReport, reason: str, rejection_id: int) -> None:
        self.report = report
        self.reason = reason
        self.rejection_id = rejection_id
        super().__init__(reason)


@dataclass(frozen=True)
class ColumnSummary:
    """One column of an uploaded dataset, aggregated — never a row."""

    name: str
    kind: str
    unit: str
    distinct: int
    minimum: int | None
    maximum: int | None
    mean: float | None


@dataclass(frozen=True)
class DatasetPreview:
    """Anonymised aggregate preview of a staged upload: counts, balance, ranges only."""

    record_count: int
    column_count: int
    class_zero: int
    class_one: int
    columns: tuple[ColumnSummary, ...]

    @property
    def class_one_rate(self) -> float:
        total = self.class_zero + self.class_one
        return (self.class_one / total) if total else 0.0


@dataclass(frozen=True)
class DatasetVersionView:
    """One ``dataset_versions`` row as the admin page sees it."""

    id: int
    original_filename_safe: str
    sha256: str
    record_count: int
    column_count: int
    class_zero: int
    class_one: int
    validated_at: str | None
    activated_at: str | None
    is_active: bool
    uploaded_by: int | None
    status: str
    quarantined_filename: str | None

    @property
    def class_one_rate(self) -> float:
        total = self.class_zero + self.class_one
        return (self.class_one / total) if total else 0.0

    @property
    def short_sha256(self) -> str:
        return self.sha256[:12]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "original_filename_safe": self.original_filename_safe,
            "sha256": self.sha256,
            "record_count": self.record_count,
            "column_count": self.column_count,
            "class_zero": self.class_zero,
            "class_one": self.class_one,
            "class_one_rate": self.class_one_rate,
            "validated_at": self.validated_at,
            "activated_at": self.activated_at,
            "is_active": self.is_active,
            "uploaded_by": self.uploaded_by,
            "status": self.status,
            "quarantined_filename": self.quarantined_filename,
        }


@dataclass(frozen=True)
class StagedDataset:
    """Outcome of an upload: the version row, its aggregate preview, and whether it was new."""

    version: DatasetVersionView
    preview: DatasetPreview | None
    duplicate: bool


_VERSION_COLUMNS = (
    "id, original_filename_safe, sha256, record_count, column_count, class_zero, class_one, "
    "validated_at, activated_at, is_active, uploaded_by, status, quarantined_filename"
)


def _view(row: sqlite3.Row) -> DatasetVersionView:
    return DatasetVersionView(
        id=int(row["id"]),
        original_filename_safe=row["original_filename_safe"],
        sha256=row["sha256"],
        record_count=int(row["record_count"]),
        column_count=int(row["column_count"]),
        class_zero=int(row["class_zero"]),
        class_one=int(row["class_one"]),
        validated_at=row["validated_at"],
        activated_at=row["activated_at"],
        is_active=bool(row["is_active"]),
        uploaded_by=row["uploaded_by"],
        status=row["status"],
        quarantined_filename=row["quarantined_filename"],
    )


def _admin(
    conn: sqlite3.Connection, token: str | None, *, now: datetime | None, action: str
) -> Principal:
    """The guard every privileged function here calls first."""
    return security.require_role(conn, token, ("admin",), now=now, action=action)


def _version_row(conn: sqlite3.Connection, version_id: int) -> sqlite3.Row:
    row = conn.execute(
        f"SELECT {_VERSION_COLUMNS} FROM dataset_versions WHERE id = ?", (int(version_id),)
    ).fetchone()
    if row is None:
        raise PolicyViolation("No such dataset version.")
    return row


def _active_row(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        f"SELECT {_VERSION_COLUMNS} FROM dataset_versions WHERE is_active = 1"
    ).fetchone()


# --------------------------------------------------------------------------- preview
def aggregate_preview(payload: bytes) -> DatasetPreview:
    """Summarise an **already validated** CSV without exposing a single row.

    Counts, class balance, and per-column min/max/mean/distinct only. The caller is expected
    to have validated ``payload`` first; this function does not re-check the contract.
    """
    frame = pd.read_csv(io.BytesIO(payload), encoding="utf-8-sig")
    target = pd.to_numeric(frame[TARGET_COLUMN], errors="coerce")
    summaries: list[ColumnSummary] = []
    for spec in COLUMN_SPECS:
        if spec.name not in frame.columns:
            summaries.append(ColumnSummary(spec.name, spec.kind, spec.unit, 0, None, None, None))
            continue
        series = pd.to_numeric(frame[spec.name], errors="coerce").dropna()
        if series.empty:
            summaries.append(ColumnSummary(spec.name, spec.kind, spec.unit, 0, None, None, None))
            continue
        summaries.append(
            ColumnSummary(
                name=spec.name,
                kind=spec.kind,
                unit=spec.unit,
                distinct=int(series.nunique()),
                minimum=int(series.min()),
                maximum=int(series.max()),
                mean=round(float(series.mean()), 2),
            )
        )
    return DatasetPreview(
        record_count=int(len(frame)),
        column_count=int(len(frame.columns)),
        class_zero=int((target == 0).sum()),
        class_one=int((target == 1).sum()),
        columns=tuple(summaries),
    )


def schema_rows() -> list[dict[str, str]]:
    """The 25-column contract as the page renders it. Static facts, no data."""
    rows: list[dict[str, str]] = []
    for spec in COLUMN_SPECS:
        codes = (
            ", ".join(str(int(code)) for code in sorted(spec.allowed))
            if spec.allowed is not None
            else "—"
        )
        if spec.minimum is not None and spec.maximum is not None:
            bounds = f"{spec.minimum} … {spec.maximum}"
        elif spec.minimum is not None:
            bounds = f"≥ {spec.minimum}"
        elif spec.maximum is not None:
            bounds = f"≤ {spec.maximum}"
        else:
            bounds = "—"
        rows.append(
            {
                "column": spec.name,
                "role": spec.kind,
                "unit": spec.unit,
                "documented codes": codes,
                "validated range": bounds,
                "used by the 23-feature form": "yes" if spec.is_feature else "no",
            }
        )
    return rows


# ------------------------------------------------------------------------ rejections
def _rejection_reason(report: validation.ValidationReport) -> str:
    """The message shown to the admin and stored: the problems, never a cell value."""
    if not report.errors:
        return "the upload was rejected"
    parts = [error.message for error in report.errors[:4]]
    if len(report.errors) > 4:
        parts.append(f"…and {len(report.errors) - 4} more problem(s)")
    reason = "; ".join(parts)
    return reason if len(reason) <= MAX_REASON_CHARS else reason[: MAX_REASON_CHARS - 1] + "…"


def _record_rejection(
    conn: sqlite3.Connection,
    *,
    actor_user_id: int | None,
    report: validation.ValidationReport,
    original_filename_safe: str,
    quarantined_filename: str | None,
    sha256: str,
    size_bytes: int,
    moment: datetime,
) -> int:
    """Persist one rejection and its audit row. Returns the rejection id."""
    codes = ",".join(sorted(report.codes)) or "unknown"
    reason = _rejection_reason(report)
    with transaction(conn):
        cursor = conn.execute(
            "INSERT INTO dataset_rejections (original_filename_safe, quarantined_filename, "
            "sha256, size_bytes, error_codes, reason, uploaded_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                original_filename_safe,
                quarantined_filename,
                sha256,
                int(size_bytes),
                codes,
                reason,
                actor_user_id,
                to_iso(moment),
            ),
        )
        rejection_id = int(cursor.lastrowid)
        audit.append(
            conn,
            action="dataset.rejected",
            actor_user_id=actor_user_id,
            entity_type="dataset_rejection",
            entity_id=rejection_id,
            details={
                "codes": codes,
                "quarantined_filename": quarantined_filename,
                "size_bytes": int(size_bytes),
                "retraining_triggered": False,
                "model_replaced": False,
            },
            now=moment,
        )
    return rejection_id


def _remove_quarantine(quarantined: validation.QuarantinedUpload | None) -> None:
    """Drop the quarantined copy of a rejected upload once it is recorded.

    Retention of an *invalid* upload has no purpose beyond diagnosis, and the diagnosis is
    the stored reason. The staged (valid) copies are kept: they are what a retraining run
    would read.
    """
    if quarantined is None:
        return
    try:
        quarantined.path.unlink(missing_ok=True)
    except OSError:  # pragma: no cover - a read-only volume must not lose the record
        pass


# ----------------------------------------------------------------------------- reads
def list_versions(
    conn: sqlite3.Connection, token: str | None, *, now: datetime | None = None
) -> list[DatasetVersionView]:
    """Every dataset version, newest first. Admin only."""
    _admin(conn, token, now=now, action="data_manager.list_versions")
    rows = conn.execute(
        f"SELECT {_VERSION_COLUMNS} FROM dataset_versions ORDER BY id DESC"
    ).fetchall()
    return [_view(row) for row in rows]


def active_version(
    conn: sqlite3.Connection, token: str | None, *, now: datetime | None = None
) -> DatasetVersionView | None:
    """The single active dataset version, or ``None``. Admin only."""
    _admin(conn, token, now=now, action="data_manager.active_version")
    row = _active_row(conn)
    return None if row is None else _view(row)


def list_rejections(
    conn: sqlite3.Connection, token: str | None, *, limit: int = 25, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Newest-first rejection log. Admin only; reasons carry no cell values."""
    _admin(conn, token, now=now, action="data_manager.list_rejections")
    if limit < 1:
        return []
    rows = conn.execute(
        "SELECT id, original_filename_safe, quarantined_filename, sha256, size_bytes, "
        "error_codes, reason, uploaded_by, created_at FROM dataset_rejections "
        "ORDER BY id DESC LIMIT ?",
        (int(limit),),
    ).fetchall()
    return [dict(row) for row in rows]


def deployed_model_facts(models_dir: Path | str = DEFAULT_MODELS_DIR) -> dict[str, Any]:
    """What the artifact on disk says about the dataset that built it.

    Reads the manifest and re-hashes the artifact; it does not verify the artifact (that is
    :mod:`ml.verify_artifact`, run by the loader) and it changes nothing. Returns
    ``available: False`` rather than raising when the artifacts are absent.
    """
    directory = Path(models_dir)
    manifest_path = directory / MANIFEST_NAME
    artifact_path = directory / ARTIFACT_NAME
    facts: dict[str, Any] = {
        "available": False,
        "models_dir": str(directory),
        "model_version": None,
        "artifact_sha256_recorded": None,
        "artifact_sha256_now": None,
        "artifact_matches_manifest": None,
        "dataset_sha256": None,
        "dataset_path": None,
        "trained_at": None,
        "manifest_readable": False,
    }
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return facts
    facts["manifest_readable"] = True
    artifact = manifest.get("artifact") or {}
    dataset = manifest.get("dataset") or {}
    model = manifest.get("model") or {}
    facts.update(
        {
            "model_version": model.get("version"),
            "artifact_sha256_recorded": artifact.get("sha256"),
            "dataset_sha256": dataset.get("sha256"),
            "dataset_path": dataset.get("path"),
            "trained_at": manifest.get("created_at"),
        }
    )
    try:
        facts["artifact_sha256_now"] = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    except OSError:
        facts["artifact_sha256_now"] = None
    facts["available"] = bool(facts["dataset_sha256"])
    facts["artifact_matches_manifest"] = (
        facts["artifact_sha256_now"] is not None
        and facts["artifact_sha256_now"] == facts["artifact_sha256_recorded"]
    )
    return facts


def comparison(
    conn: sqlite3.Connection,
    token: str | None,
    *,
    models_dir: Path | str = DEFAULT_MODELS_DIR,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The staged-vs-deployed panel's facts. Admin only.

    ``active_built_the_model`` is true only when the active pointer names the same bytes as
    the manifest's dataset — the honest statement the card asks for.
    """
    _admin(conn, token, now=now, action="data_manager.comparison")
    active = _active_row(conn)
    deployed = deployed_model_facts(models_dir)
    return {
        "deployed": deployed,
        "active": None if active is None else _view(active).as_dict(),
        "active_built_the_model": bool(
            active is not None and deployed.get("dataset_sha256") == active["sha256"]
        ),
    }


# ---------------------------------------------------------------------------- writes
def stage_upload(
    conn: sqlite3.Connection,
    token: str | None,
    payload: bytes,
    original_filename: str | None = None,
    *,
    quarantine_dir: Path | str = validation.DEFAULT_QUARANTINE_DIR,
    max_bytes: int = validation.MAX_UPLOAD_BYTES,
    now: datetime | None = None,
) -> StagedDataset:
    """Quarantine and validate one upload, then record it as a *staged* version.

    A rejected upload raises :class:`DatasetRejected` (carrying the full report) after the
    rejection row and audit row are written. Nothing is activated here and nothing is
    retrained: staging only records metadata.
    """
    actor = _admin(conn, token, now=now, action="data_manager.stage_upload")
    moment = now or utcnow()
    label = validation.sanitize_filename(original_filename)

    quarantined: validation.QuarantinedUpload | None = None
    try:
        quarantined, report = validation.ingest_upload(
            payload, original_filename, quarantine_dir=quarantine_dir, max_bytes=max_bytes
        )
    except validation.ValidationError as error:
        # Empty or oversize: nothing was written, but the attempt is still recorded.
        report = validation.ValidationReport()
        report.fail(error.code, error.message, column=error.column, rows=error.rows)

    digest = hashlib.sha256(payload or b"").hexdigest()

    if not report.ok:
        rejection_id = _record_rejection(
            conn,
            actor_user_id=actor.user_id,
            report=report,
            original_filename_safe=label,
            quarantined_filename=None if quarantined is None else quarantined.generated_filename,
            sha256=digest,
            size_bytes=len(payload or b""),
            moment=moment,
        )
        _remove_quarantine(quarantined)
        raise DatasetRejected(report, _rejection_reason(report), rejection_id)

    assert quarantined is not None  # a clean report always has a quarantined copy
    preview = aggregate_preview(payload)

    existing = conn.execute(
        f"SELECT {_VERSION_COLUMNS} FROM dataset_versions WHERE sha256 = ?", (report.sha256,)
    ).fetchone()
    if existing is not None:
        # Same bytes, already staged: idempotent, and the redundant copy is dropped.
        _remove_quarantine(quarantined)
        return StagedDataset(version=_view(existing), preview=preview, duplicate=True)

    with transaction(conn):
        cursor = conn.execute(
            "INSERT INTO dataset_versions (original_filename_safe, sha256, record_count, "
            "column_count, class_zero, class_one, validated_at, activated_at, is_active, "
            "uploaded_by, status, quarantined_filename) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0, ?, ?, ?)",
            (
                quarantined.original_filename_safe,
                report.sha256,
                report.record_count,
                report.column_count,
                report.class_zero,
                report.class_one,
                to_iso(moment),
                actor.user_id,
                STATUS_VALIDATED,
                quarantined.generated_filename,
            ),
        )
        version_id = int(cursor.lastrowid)
        audit.append(
            conn,
            action="dataset.staged",
            actor_user_id=actor.user_id,
            entity_type="dataset_version",
            entity_id=version_id,
            details={
                "sha256": report.sha256,
                "record_count": report.record_count,
                "class_zero": report.class_zero,
                "class_one": report.class_one,
                "quarantined_filename": quarantined.generated_filename,
                "retraining_triggered": False,
                "model_replaced": False,
            },
            now=moment,
        )
    return StagedDataset(version=_view(_version_row(conn, version_id)), preview=preview, duplicate=False)


def activate_version(
    conn: sqlite3.Connection,
    token: str | None,
    version_id: int,
    *,
    now: datetime | None = None,
) -> DatasetVersionView:
    """Make one staged version the active pointer, in a single transaction.

    This changes **only** which dataset a future retraining run would use. The model in
    service is not touched: no artifact is read, written or reloaded here.
    """
    actor = _admin(conn, token, now=now, action="data_manager.activate_version")
    moment = now or utcnow()

    with transaction(conn):
        target = _version_row(conn, version_id)
        previous = _active_row(conn)
        if bool(target["is_active"]):
            return _view(target)
        if target["status"] not in (STATUS_VALIDATED, STATUS_ACTIVATED):
            raise PolicyViolation("Only a validated dataset can be activated.")
        conn.execute(
            "UPDATE dataset_versions SET is_active = 0 WHERE is_active = 1 AND id <> ?",
            (int(version_id),),
        )
        conn.execute(
            "UPDATE dataset_versions SET is_active = 1, status = ?, "
            "activated_at = COALESCE(activated_at, ?) WHERE id = ?",
            (STATUS_ACTIVATED, to_iso(moment), int(version_id)),
        )
        audit.append(
            conn,
            action="dataset.activated",
            actor_user_id=actor.user_id,
            entity_type="dataset_version",
            entity_id=int(version_id),
            details={
                "sha256": target["sha256"],
                "previous_dataset_id": None if previous is None else int(previous["id"]),
                "previous_sha256": None if previous is None else previous["sha256"],
                "retraining_triggered": False,
                "model_replaced": False,
            },
            now=moment,
        )
    return _view(_version_row(conn, version_id))


def ensure_seed_version(
    conn: sqlite3.Connection,
    *,
    seed_path: Path | str = DEFAULT_SEED_PATH,
    now: datetime | None = None,
) -> DatasetVersionView | None:
    """Record the immutable benchmark dataset as a version, once, and point at it if idle.

    Called at startup. Idempotent by checksum: the seed is registered the first time only, and
    an operator's later activation is never overridden. It does not train and does not copy
    the file — ``data/UCI_Credit_Card.csv`` is already the immutable seed.
    """
    path = Path(seed_path)
    try:
        payload = path.read_bytes()
    except OSError:
        return None
    digest = hashlib.sha256(payload).hexdigest()
    moment = now or utcnow()

    existing = conn.execute(
        f"SELECT {_VERSION_COLUMNS} FROM dataset_versions WHERE sha256 = ?", (digest,)
    ).fetchone()
    if existing is not None:
        if _active_row(conn) is None:
            # The version is known but nothing is active (a first run that stopped early, or an
            # operator who cleared the pointer): adopt it. The seed is the model's own dataset.
            return _adopt_active(conn, int(existing["id"]), moment)
        return _view(existing)

    report = validation.validate_csv_bytes(payload, filename=path.name)
    if not report.ok:  # pragma: no cover - the shipped seed is valid by construction
        return None

    with transaction(conn):
        has_active = _active_row(conn) is not None
        cursor = conn.execute(
            "INSERT INTO dataset_versions (original_filename_safe, sha256, record_count, "
            "column_count, class_zero, class_one, validated_at, activated_at, is_active, "
            "uploaded_by, status, quarantined_filename) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, NULL)",
            (
                path.name,
                digest,
                report.record_count,
                report.column_count,
                report.class_zero,
                report.class_one,
                to_iso(moment),
                to_iso(moment) if not has_active else None,
                0 if has_active else 1,
                STATUS_VALIDATED if has_active else STATUS_ACTIVATED,
            ),
        )
        version_id = int(cursor.lastrowid)
        audit.append(
            conn,
            action="dataset.seeded",
            actor_user_id=None,
            entity_type="dataset_version",
            entity_id=version_id,
            details={
                "sha256": digest,
                "record_count": report.record_count,
                "is_active": not has_active,
                "retraining_triggered": False,
            },
            now=moment,
        )
    return _view(_version_row(conn, version_id))


def _adopt_active(
    conn: sqlite3.Connection, version_id: int, moment: datetime
) -> DatasetVersionView:
    """Point at an already-registered version because no dataset is active. System act."""
    with transaction(conn):
        if _active_row(conn) is not None:  # another writer won; keep their pointer
            return _view(_version_row(conn, version_id))
        conn.execute(
            "UPDATE dataset_versions SET is_active = 1, status = ?, "
            "activated_at = COALESCE(activated_at, ?) WHERE id = ?",
            (STATUS_ACTIVATED, to_iso(moment), int(version_id)),
        )
        audit.append(
            conn,
            action="dataset.seeded_active",
            actor_user_id=None,
            entity_type="dataset_version",
            entity_id=int(version_id),
            details={"retraining_triggered": False},
            now=moment,
        )
    return _view(_version_row(conn, version_id))


__all__ = [
    "ARTIFACT_NAME",
    "COLUMNS",
    "ColumnSummary",
    "DEFAULT_MODELS_DIR",
    "DEFAULT_SEED_PATH",
    "DatasetPreview",
    "DatasetRejected",
    "DatasetVersionView",
    "MANIFEST_NAME",
    "STATUS_ACTIVATED",
    "STATUS_VALIDATED",
    "StagedDataset",
    "activate_version",
    "active_version",
    "aggregate_preview",
    "comparison",
    "deployed_model_facts",
    "ensure_seed_version",
    "list_rejections",
    "list_versions",
    "schema_rows",
    "stage_upload",
]
