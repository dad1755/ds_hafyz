"""SQLite storage: one connection policy, one idempotent migration ladder.

Blueprint §6 "Database design (SQLite)" and §9 SPRINT 6. The rules this module exists to
enforce, and nothing else:

* **One file, one volume.** The database lives at ``/app/storage/aihubcampus.db`` (compose
  sets ``APP_DB_PATH``; ``src.config`` already carries the default), i.e. on the
  ``app_storage`` named volume, never inside the image.
* **WAL and a busy timeout.** Readers never block the writer and a second process waits
  instead of failing with ``database is locked``. ``foreign_keys=ON`` so the schema's
  references mean something, and ``isolation_level=None`` so this module — not the driver's
  implicit transaction handling — decides where a transaction starts and ends.
* **Idempotent startup.** :func:`migrate` applies only the versions absent from
  ``schema_migrations``, each inside its own ``BEGIN IMMEDIATE`` transaction. Running it on
  every process start (and twice in a row) is a no-op, which is what makes a container
  restart safe.
* **Parameterised SQL only.** Every statement in ``src/`` that takes a value binds it with
  ``?``; no query is ever assembled from user input.

Timestamps are stored as fixed-width UTC ISO-8601 text (``2026-10-26T04:05:06Z``). The
format is deliberately boring: it sorts lexicographically, it is unambiguous about the zone,
and it reads correctly in a SQLite browser during the demo.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from src.config import load_settings

#: How long a statement waits for a competing writer before SQLite raises.
BUSY_TIMEOUT_MS = 5_000

#: ISO-8601, seconds resolution, always UTC.
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utcnow() -> datetime:
    """Timezone-aware 'now'. Tests pass an explicit value instead of sleeping."""
    return datetime.now(timezone.utc)


def to_iso(moment: datetime) -> str:
    """Render ``moment`` in the stored format (naive input is taken as UTC)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime(TS_FORMAT)


def from_iso(text: str) -> datetime:
    """Parse a stored timestamp. Raises ``ValueError`` on anything else."""
    return datetime.strptime(text, TS_FORMAT).replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- migrations
# Each entry is (version, statements). A version is applied exactly once, in order, in one
# transaction; a failing statement rolls the whole version back. Never edit a version that
# has shipped — add the next one.
MIGRATIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "0001_core_tables",
        (
            # Users. `role` and the two boolean columns are constrained in the schema so a
            # bug cannot write a third role or a NULL that reads as truthy.
            """
            CREATE TABLE users (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                username             TEXT    NOT NULL,
                display_name         TEXT    NOT NULL DEFAULT '',
                password_hash        TEXT    NOT NULL,
                role                 TEXT    NOT NULL CHECK (role IN ('admin', 'user')),
                is_active            INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                must_change_password INTEGER NOT NULL DEFAULT 0
                                              CHECK (must_change_password IN (0, 1)),
                created_at           TEXT    NOT NULL,
                updated_at           TEXT    NOT NULL,
                last_login_at        TEXT
            )
            """,
            # Case-insensitive uniqueness without a second column: `Ds_Hafyz` and `ds_hafyz`
            # are the same account, so a lookalike cannot be created to confuse an operator.
            "CREATE UNIQUE INDEX users_username_lower_key ON users (lower(username))",
            # Prediction history. Pseudonymous by user id; no raw 23-feature snapshot
            # (blueprint §6, threat T11). Written from S7 onwards.
            """
            CREATE TABLE prediction_logs (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id             INTEGER NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
                predicted_class     INTEGER NOT NULL CHECK (predicted_class IN (0, 1)),
                default_probability REAL    NOT NULL
                                            CHECK (default_probability >= 0.0
                                                   AND default_probability <= 1.0),
                risk_tier           TEXT    NOT NULL,
                model_version       TEXT    NOT NULL,
                created_at          TEXT    NOT NULL
            )
            """,
            # The listing a user's own history runs: filter by user, newest first.
            "CREATE INDEX prediction_logs_user_time ON prediction_logs (user_id, created_at DESC)",
            """
            CREATE TABLE dataset_versions (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                original_filename_safe TEXT    NOT NULL,
                sha256                 TEXT    NOT NULL UNIQUE,
                record_count           INTEGER NOT NULL,
                column_count           INTEGER NOT NULL,
                class_zero             INTEGER NOT NULL,
                class_one              INTEGER NOT NULL,
                validated_at           TEXT,
                activated_at           TEXT,
                is_active              INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
                uploaded_by            INTEGER REFERENCES users (id) ON DELETE SET NULL,
                status                 TEXT    NOT NULL
            )
            """,
            # At most one active dataset, enforced by the database as well as by the
            # transaction in S9: a partial unique index cannot be raced.
            "CREATE UNIQUE INDEX dataset_versions_one_active "
            "ON dataset_versions (is_active) WHERE is_active = 1",
            """
            CREATE TABLE audit_events (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_user_id         INTEGER REFERENCES users (id) ON DELETE SET NULL,
                action                TEXT    NOT NULL,
                entity_type           TEXT,
                entity_id             TEXT,
                created_at            TEXT    NOT NULL,
                non_sensitive_details TEXT    NOT NULL DEFAULT '{}'
            )
            """,
            "CREATE INDEX audit_events_time ON audit_events (created_at DESC)",
        ),
    ),
    (
        "0002_auth_sessions",
        (
            # Server-side sessions. The primary key is the SHA-256 of the bearer token, so a
            # read of this table cannot be replayed as a cookie, and logout/expiry/deactivation
            # are checked against the database on every privileged call rather than trusted
            # from Streamlit's session state.
            """
            CREATE TABLE sessions (
                token_hash   TEXT    PRIMARY KEY,
                user_id      INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                created_at   TEXT    NOT NULL,
                expires_at   TEXT    NOT NULL,
                last_seen_at TEXT    NOT NULL,
                revoked_at   TEXT
            )
            """,
            "CREATE INDEX sessions_user ON sessions (user_id)",
            "CREATE INDEX sessions_expiry ON sessions (expires_at)",
            # Login throttle: one row per failed attempt, counted inside a window and pruned
            # as it ages, so the lock expires by itself instead of needing a reset job.
            """
            CREATE TABLE login_attempts (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                username_lower TEXT    NOT NULL,
                attempted_at   TEXT    NOT NULL,
                succeeded      INTEGER NOT NULL DEFAULT 0 CHECK (succeeded IN (0, 1))
            )
            """,
            "CREATE INDEX login_attempts_lookup ON login_attempts (username_lower, attempted_at)",
        ),
    ),
    (
        "0003_dataset_staging",
        (
            # The generated quarantine name of a staged dataset, so an operator can find the
            # copy that was actually validated. Never the uploaded name — that one is a label
            # only (validation.sanitize_filename) and never builds a path.
            "ALTER TABLE dataset_versions ADD COLUMN quarantined_filename TEXT",
            # Rejected uploads are logged, not versioned: they have no counts and no columns,
            # and their bytes must not block a corrected re-upload under the sha256 unique
            # index. The reason is the same message the admin saw, which names columns and
            # row counts but never a cell value.
            """
            CREATE TABLE dataset_rejections (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                original_filename_safe TEXT    NOT NULL,
                quarantined_filename   TEXT,
                sha256                 TEXT    NOT NULL,
                size_bytes             INTEGER NOT NULL,
                error_codes            TEXT    NOT NULL,
                reason                 TEXT    NOT NULL,
                uploaded_by            INTEGER REFERENCES users (id) ON DELETE SET NULL,
                created_at             TEXT    NOT NULL
            )
            """,
            "CREATE INDEX dataset_rejections_time ON dataset_rejections (created_at DESC)",
        ),
    ),
)

#: Table the ladder itself is recorded in. Created before any version is applied.
SCHEMA_MIGRATIONS_DDL = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
)


def resolve_db_path(path: str | Path | None = None) -> Path:
    """Return the database path: explicit argument, else ``APP_DB_PATH``, else the default."""
    if path is not None:
        return Path(path)
    return Path(load_settings().db_path)


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Open a connection with the project's pragmas and row access by column name.

    The parent directory is created (mode 0755) if missing, so a fresh volume works. Each
    call returns a new connection: SQLite connections are cheap, and one per unit of work
    avoids sharing a handle across Streamlit's rerun threads.
    """
    db_path = resolve_db_path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        db_path,
        timeout=BUSY_TIMEOUT_MS / 1000,
        isolation_level=None,  # explicit transactions only; see `transaction()`
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """A write transaction that takes the write lock immediately.

    ``BEGIN IMMEDIATE`` rather than the default deferred begin: a transaction that starts by
    reading and then writes can fail late with ``database is locked`` under concurrency,
    whereas this one waits for the lock up front (bounded by ``busy_timeout``).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    conn.commit()


def applied_versions(conn: sqlite3.Connection) -> list[str]:
    """Versions recorded in ``schema_migrations``, oldest first."""
    rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return [row["version"] for row in rows]


def pending_versions(conn: sqlite3.Connection) -> list[str]:
    """Versions in :data:`MIGRATIONS` that this database has not applied yet."""
    done = set(applied_versions(conn))
    return [version for version, _ in MIGRATIONS if version not in done]


def migrate(conn: sqlite3.Connection) -> list[str]:
    """Apply pending migrations; return the versions applied by this call.

    Idempotent: a second call on the same database applies nothing and returns ``[]``.
    Each version is one transaction, so a crash mid-ladder leaves the database at the last
    complete version rather than half-upgraded.
    """
    conn.execute(SCHEMA_MIGRATIONS_DDL)
    applied: list[str] = []
    for version, statements in MIGRATIONS:
        if version in applied_versions(conn):
            continue
        with transaction(conn):
            for statement in statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, to_iso(utcnow())),
            )
        applied.append(version)
    return applied


def purge_expired_sessions(conn: sqlite3.Connection, *, now: datetime | None = None) -> int:
    """Delete sessions that expired more than a day ago; return how many were removed.

    Called from the setup script, never from a request: housekeeping should not sit in the
    path of a sign-in. ``now`` is injectable so the behaviour is testable without sleeping.
    """
    cutoff = to_iso((now or utcnow()) - timedelta(days=1))
    cursor = conn.execute("DELETE FROM sessions WHERE expires_at < ?", (cutoff,))
    return cursor.rowcount
