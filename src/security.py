"""Authentication, server-side sessions and role guards (blueprint §2; §9 SPRINT 6).

Three properties this module is built to guarantee, each with a test in
``tests/test_security.py``:

* **Passwords are never stored, compared or logged in the clear.** They are hashed with
  Argon2id (``argon2-cffi``, the vetted library the blueprint allows) and verified through the
  library's constant-time comparison. There is no SHA-256 code path anywhere, and
  :func:`verify_password` returns a bool rather than a reason, so a caller cannot leak *why*
  a password failed.
* **A session is a row, not a Streamlit variable.** :func:`login` returns an opaque token
  whose SHA-256 is the primary key of a ``sessions`` row carrying an expiry, a revocation
  timestamp and a user id. :func:`resolve_session` re-reads that row and the user's
  ``is_active`` flag on **every** call, so sign-out, expiry and deactivation take effect
  immediately even if a browser tab keeps its old state.
* **Authorisation is checked inside the function that does the work.** :func:`require_role`
  is called by every privileged function in :mod:`src.accounts` as its first statement, so
  hiding a page in the UI is a convenience, never the control. A direct call with a user
  token raises :class:`PermissionDenied` and is written to the audit trail.

Brute force is slowed by a SQLite-backed counter: :data:`THROTTLE_MAX_FAILURES` failures for
one username inside :data:`THROTTLE_WINDOW` lock that username for
:data:`THROTTLE_LOCKOUT`. The lock expires by itself because the timestamps age out; there is
no flag to reset and no job to run. Failures are counted per username, not per IP — the app
sits behind a tunnel and never sees a trustworthy client address.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Iterable, Sequence

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from src import audit
from src.db import from_iso, to_iso, transaction, utcnow

# ------------------------------------------------------------------------------ policy
#: Minimum length for a *new* password. The blueprint's range is 8–12+; 12 is the top of it
#: and costs nothing here. The operator's seeded password is 7 characters, which is why
#: seeding forces a change on first sign-in (docs/architecture.md §14, D13).
MIN_PASSWORD_LENGTH = 12

#: Upper bound on a submitted password. Argon2 cost grows with input; this stops a multi-
#: megabyte "password" from becoming a denial-of-service vector.
MAX_PASSWORD_LENGTH = 256

#: A short denylist of the passwords a demo would actually attract. Not a substitute for a
#: real breach corpus — a documented limitation, not a claim of strength checking.
COMMON_PASSWORDS = frozenset(
    {
        "password", "password1", "password123", "passw0rd", "123456789012",
        "qwertyuiop12", "letmein12345", "administrator", "adminadmin12",
        "changeme1234", "welcome12345", "aihubcampus1",
    }
)

#: Session lifetime. Absolute, not sliding: a session cannot be kept alive indefinitely by
#: clicking around, and an unattended demo laptop does not stay signed in forever.
SESSION_TTL = timedelta(hours=8)

#: Do not rewrite ``last_seen_at`` on every Streamlit rerun; once a minute is enough.
LAST_SEEN_RESOLUTION = timedelta(seconds=60)

#: Brute-force policy: 5 failures in 15 minutes locks the username for 15 minutes.
THROTTLE_MAX_FAILURES = 5
THROTTLE_WINDOW = timedelta(minutes=15)
THROTTLE_LOCKOUT = timedelta(minutes=15)

#: Old attempt rows are pruned after this long; they no longer affect any decision.
ATTEMPT_RETENTION = timedelta(days=1)

#: Argon2id parameters (OWASP's Argon2id baseline is m=19 MiB, t=2, p=1; these are stronger
#: and still ~0.1 s per verification on the deployment host). Changing them changes only the
#: cost, never the stored format, which is a PHC string: ``$argon2id$v=19$m=65536,t=3,p=4$…``.
ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST_KIB = 65_536
ARGON2_PARALLELISM = 4
ARGON2_HASH_LENGTH = 32
ARGON2_SALT_LENGTH = 16

#: The only hash format this application writes or accepts.
HASH_PREFIX = "$argon2id$"


class AuthError(Exception):
    """Base class. ``public_message`` is written for a person and never names a credential."""

    public_message = "Sign-in failed."

    def __init__(self, public_message: str | None = None) -> None:
        if public_message is not None:
            self.public_message = public_message
        super().__init__(self.public_message)


class InvalidCredentials(AuthError):
    """Wrong username *or* wrong password — deliberately the same error for both."""

    public_message = "Invalid username or password."


class AccountInactive(AuthError):
    """The account exists and the password was right, but the account is deactivated."""

    public_message = "This account is not active. Contact the administrator."


class Throttled(AuthError):
    """Too many recent failures for this username."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = max(1, int(retry_after_seconds))
        minutes = (self.retry_after_seconds + 59) // 60
        unit = "minute" if minutes == 1 else "minutes"
        super().__init__(
            f"Too many failed sign-in attempts. Try again in {minutes} {unit}."
        )


class SessionInvalid(AuthError):
    """No token, unknown token, revoked session, expired session, or deactivated user."""

    public_message = "Your session has ended. Sign in again."


class PasswordChangeRequired(AuthError):
    """The account is signed in but must set a new password before doing anything else."""

    public_message = "A password change is required before this account can continue."


class PermissionDenied(AuthError):
    """Authenticated, active, but not in a role this function allows."""

    public_message = "You do not have permission to perform this action."


class WeakPassword(AuthError):
    """A proposed password fails the policy. The message lists the rules it broke."""

    def __init__(self, reasons: Sequence[str]) -> None:
        self.reasons = list(reasons)
        super().__init__("Password does not meet the policy: " + "; ".join(self.reasons))


class PolicyViolation(AuthError):
    """A request that is well-formed but refused by an application rule."""


@dataclass(frozen=True)
class Principal:
    """Who is calling, established from the database — never from the caller's own claim.

    ``session_expires_at`` is ``None`` for a principal resolved without a session (seeding).
    No password hash and no session token is carried on this object, so it can be logged.
    """

    user_id: int
    username: str
    display_name: str
    role: str
    must_change_password: bool
    session_expires_at: datetime | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


# ------------------------------------------------------------------------- password hash
@lru_cache(maxsize=1)
def _hasher() -> PasswordHasher:
    return PasswordHasher(
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST_KIB,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LENGTH,
        salt_len=ARGON2_SALT_LENGTH,
        type=Type.ID,
    )


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    """A real hash of a random throwaway value.

    Verified against when the username does not exist, so a wrong username costs the same
    time as a wrong password and the response time does not enumerate accounts.
    """
    return _hasher().hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    """Return a PHC-format Argon2id hash with a fresh random salt."""
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"password must be at most {MAX_PASSWORD_LENGTH} characters")
    return _hasher().hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Constant-time verification. Returns ``False`` for any malformed or foreign hash."""
    if not isinstance(password_hash, str) or not password_hash:
        return False
    if not isinstance(password, str) or not password or len(password) > MAX_PASSWORD_LENGTH:
        return False
    try:
        return _hasher().verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_policy_errors(password: str) -> list[str]:
    """Return the policy rules ``password`` breaks. Never echoes the password."""
    if not isinstance(password, str):
        return ["must be text"]
    problems: list[str] = []
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        problems.append(f"at most {MAX_PASSWORD_LENGTH} characters")
    if password.strip() != password:
        problems.append("no leading or trailing spaces")
    if password.lower() in COMMON_PASSWORDS:
        problems.append("not a commonly used password")
    return problems


def assert_password_policy(password: str) -> None:
    """Raise :class:`WeakPassword` unless ``password`` satisfies the policy."""
    problems = password_policy_errors(password)
    if problems:
        raise WeakPassword(problems)


# --------------------------------------------------------------------------- throttling
def _normalise_username(username: str) -> str:
    """Trim and casefold a username for lookup. Never returns an empty string."""
    if not isinstance(username, str):
        raise InvalidCredentials()
    key = username.strip().lower()
    if not key or len(key) > 64:
        raise InvalidCredentials()
    return key


def _recent_failures(
    conn: sqlite3.Connection, key: str, now: datetime
) -> list[datetime]:
    since = to_iso(now - THROTTLE_WINDOW)
    rows = conn.execute(
        "SELECT attempted_at FROM login_attempts "
        "WHERE username_lower = ? AND succeeded = 0 AND attempted_at >= ? "
        "ORDER BY attempted_at",
        (key, since),
    ).fetchall()
    return [from_iso(row["attempted_at"]) for row in rows]


def _locked_for_seconds(conn: sqlite3.Connection, key: str, now: datetime) -> int:
    """Seconds until this username may try again; 0 when it is not locked."""
    failures = _recent_failures(conn, key, now)
    if len(failures) < THROTTLE_MAX_FAILURES:
        return 0
    unlocks_at = failures[-1] + THROTTLE_LOCKOUT
    remaining = (unlocks_at - now).total_seconds()
    return max(0, int(remaining))


def _record_failure(conn: sqlite3.Connection, key: str, now: datetime) -> None:
    with transaction(conn):
        conn.execute(
            "DELETE FROM login_attempts WHERE username_lower = ? AND attempted_at < ?",
            (key, to_iso(now - ATTEMPT_RETENTION)),
        )
        conn.execute(
            "INSERT INTO login_attempts (username_lower, attempted_at, succeeded) "
            "VALUES (?, ?, 0)",
            (key, to_iso(now)),
        )


def _clear_failures(conn: sqlite3.Connection, key: str) -> None:
    with transaction(conn):
        conn.execute(
            "DELETE FROM login_attempts WHERE username_lower = ? AND succeeded = 0", (key,)
        )


def throttle_retry_after(
    conn: sqlite3.Connection, username: str, *, now: datetime | None = None
) -> int:
    """Public read used by the UI to disable a form; 0 means 'may try now'."""
    try:
        key = _normalise_username(username)
    except InvalidCredentials:
        return 0
    return _locked_for_seconds(conn, key, now or utcnow())


# ---------------------------------------------------------------------------- sessions
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    now: datetime | None = None,
    ttl: timedelta | None = None,
) -> str:
    """Create a session row and return the raw bearer token (stored only as its SHA-256)."""
    moment = now or utcnow()
    token = secrets.token_urlsafe(32)
    with transaction(conn):
        conn.execute(
            "INSERT INTO sessions "
            "(token_hash, user_id, created_at, expires_at, last_seen_at, revoked_at) "
            "VALUES (?, ?, ?, ?, ?, NULL)",
            (
                _token_hash(token),
                int(user_id),
                to_iso(moment),
                to_iso(moment + (ttl or SESSION_TTL)),
                to_iso(moment),
            ),
        )
    return token


def _principal_from_row(row: sqlite3.Row, expires_at: datetime | None) -> Principal:
    return Principal(
        user_id=int(row["id"]),
        username=row["username"],
        display_name=row["display_name"] or row["username"],
        role=row["role"],
        must_change_password=bool(row["must_change_password"]),
        session_expires_at=expires_at,
    )


def resolve_session(
    conn: sqlite3.Connection, token: str | None, *, now: datetime | None = None
) -> Principal:
    """Turn a bearer token into a :class:`Principal`, or raise :class:`SessionInvalid`.

    Every reason for failure is the same exception and the same message: unknown token,
    revoked session, expired session, missing user, deactivated user. A caller learns only
    that it must sign in again.
    """
    moment = now or utcnow()
    if not isinstance(token, str) or not token or len(token) > 200:
        raise SessionInvalid()

    row = conn.execute(
        "SELECT u.id, u.username, u.display_name, u.role, u.is_active, "
        "u.must_change_password, s.expires_at, s.revoked_at, s.last_seen_at "
        "FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token_hash = ?",
        (_token_hash(token),),
    ).fetchone()

    if row is None or row["revoked_at"] is not None:
        raise SessionInvalid()
    expires_at = from_iso(row["expires_at"])
    if expires_at <= moment:
        raise SessionInvalid()
    if not row["is_active"]:
        raise SessionInvalid()

    last_seen = from_iso(row["last_seen_at"])
    if moment - last_seen >= LAST_SEEN_RESOLUTION:
        with transaction(conn):
            conn.execute(
                "UPDATE sessions SET last_seen_at = ? WHERE token_hash = ?",
                (to_iso(moment), _token_hash(token)),
            )

    return _principal_from_row(row, expires_at)


def require_authenticated(
    conn: sqlite3.Connection, token: str | None, *, now: datetime | None = None
) -> Principal:
    """A valid session whose account has finished any forced password change."""
    principal = resolve_session(conn, token, now=now)
    if principal.must_change_password:
        raise PasswordChangeRequired()
    return principal


def require_role(
    conn: sqlite3.Connection,
    token: str | None,
    roles: Iterable[str],
    *,
    now: datetime | None = None,
    action: str = "authorise",
) -> Principal:
    """Authorise a privileged call: valid session, active account, allowed role.

    This is the single gate every privileged function calls first. A denial is audited with
    the acting user id, so an attempt to reach admin data with a user session is visible in
    the audit trail even though it changed nothing.
    """
    allowed = frozenset(roles)
    principal = require_authenticated(conn, token, now=now)
    if principal.role not in allowed:
        audit.append(
            conn,
            action="auth.denied",
            actor_user_id=principal.user_id,
            entity_type="role",
            entity_id=principal.role,
            details={
                "required": ",".join(sorted(allowed)),
                "attempted": action,
            },
            now=now,
        )
        raise PermissionDenied()
    return principal


def logout(conn: sqlite3.Connection, token: str | None, *, now: datetime | None = None) -> None:
    """Revoke this session. A second call with the same token is a silent no-op."""
    moment = now or utcnow()
    if not isinstance(token, str) or not token:
        return
    # Resolve before revoking, so the audit row can name the account that signed out. An
    # already-invalid token is not an error: sign-out must always be safe to click.
    try:
        principal = resolve_session(conn, token, now=moment)
    except AuthError:
        principal = None
    with transaction(conn):
        conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
            (to_iso(moment), _token_hash(token)),
        )
    if principal is not None:
        audit.append(
            conn,
            action="session.revoked",
            actor_user_id=principal.user_id,
            entity_type="session",
            entity_id=principal.user_id,
            details={"reason": "logout"},
            now=moment,
        )
    return None


# ---------------------------------------------------------------------- authentication
def authenticate(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    *,
    now: datetime | None = None,
) -> Principal:
    """Check a username/password pair against the database; return the principal.

    Does **not** create a session — :func:`login` does that. Raises
    :class:`InvalidCredentials`, :class:`AccountInactive` or :class:`Throttled`.
    """
    moment = now or utcnow()
    key = _normalise_username(username)

    locked_for = _locked_for_seconds(conn, key, moment)
    if locked_for:
        audit.append(
            conn,
            action="login.throttled",
            entity_type="username",
            entity_id=key,
            details={"retry_after_seconds": locked_for},
            now=moment,
        )
        raise Throttled(locked_for)

    row = conn.execute(
        "SELECT id, username, display_name, password_hash, role, is_active, "
        "must_change_password FROM users WHERE lower(username) = ?",
        (key,),
    ).fetchone()

    if row is None:
        # Spend the same time as a real verification so a missing username is not detectable
        # by response time, then record the failure against the name that was tried.
        verify_password(_dummy_hash(), password if isinstance(password, str) else "")
        _record_failure(conn, key, moment)
        audit.append(
            conn,
            action="login.failed",
            entity_type="username",
            entity_id=key,
            details={"reason": "unknown_user"},
            now=moment,
        )
        raise InvalidCredentials()

    if not verify_password(row["password_hash"], password):
        _record_failure(conn, key, moment)
        audit.append(
            conn,
            action="login.failed",
            actor_user_id=int(row["id"]),
            entity_type="user",
            entity_id=int(row["id"]),
            details={"reason": "bad_password"},
            now=moment,
        )
        raise InvalidCredentials()

    # The password is correct from here on, so naming the account's state reveals nothing to
    # someone who did not already know the password.
    if not row["is_active"]:
        _record_failure(conn, key, moment)
        audit.append(
            conn,
            action="login.failed",
            actor_user_id=int(row["id"]),
            entity_type="user",
            entity_id=int(row["id"]),
            details={"reason": "inactive"},
            now=moment,
        )
        raise AccountInactive()

    _clear_failures(conn, key)
    with transaction(conn):
        conn.execute(
            "UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?",
            (to_iso(moment), to_iso(moment), int(row["id"])),
        )
    audit.append(
        conn,
        action="login.succeeded",
        actor_user_id=int(row["id"]),
        entity_type="user",
        entity_id=int(row["id"]),
        details={"role": row["role"]},
        now=moment,
    )
    return _principal_from_row(row, None)


def login(
    conn: sqlite3.Connection,
    username: str,
    password: str,
    *,
    now: datetime | None = None,
    ttl: timedelta | None = None,
) -> tuple[Principal, str]:
    """Authenticate and open a session. Returns ``(principal, token)``."""
    moment = now or utcnow()
    principal = authenticate(conn, username, password, now=moment)
    token = create_session(conn, principal.user_id, now=moment, ttl=ttl)
    audit.append(
        conn,
        action="session.created",
        actor_user_id=principal.user_id,
        entity_type="session",
        entity_id=principal.user_id,
        details={"expires_at": to_iso(moment + (ttl or SESSION_TTL))},
        now=moment,
    )
    return principal, token


def change_password(
    conn: sqlite3.Connection,
    token: str | None,
    current_password: str,
    new_password: str,
    *,
    now: datetime | None = None,
) -> Principal:
    """Set a new password for the signed-in account and clear any forced-change flag.

    Allowed while ``must_change_password`` is set — this is the one function that is. Every
    other session belonging to the account is revoked, so a password change ends any other
    signed-in tab.
    """
    moment = now or utcnow()
    principal = resolve_session(conn, token, now=moment)

    row = conn.execute(
        "SELECT password_hash FROM users WHERE id = ?", (principal.user_id,)
    ).fetchone()
    if row is None:
        raise SessionInvalid()
    if not verify_password(row["password_hash"], current_password):
        audit.append(
            conn,
            action="password.change_failed",
            actor_user_id=principal.user_id,
            entity_type="user",
            entity_id=principal.user_id,
            details={"reason": "wrong_current_password"},
            now=moment,
        )
        raise InvalidCredentials()

    if verify_password(row["password_hash"], new_password):
        raise WeakPassword(["must differ from the current password"])
    assert_password_policy(new_password)

    new_hash = hash_password(new_password)
    with transaction(conn):
        conn.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0, updated_at = ? "
            "WHERE id = ?",
            (new_hash, to_iso(moment), principal.user_id),
        )
        conn.execute(
            "UPDATE sessions SET revoked_at = ? "
            "WHERE user_id = ? AND revoked_at IS NULL AND token_hash <> ?",
            (to_iso(moment), principal.user_id, _token_hash(token or "")),
        )
    audit.append(
        conn,
        action="password.changed",
        actor_user_id=principal.user_id,
        entity_type="user",
        entity_id=principal.user_id,
        details={"self_service": True},
        now=moment,
    )
    return Principal(
        user_id=principal.user_id,
        username=principal.username,
        display_name=principal.display_name,
        role=principal.role,
        must_change_password=False,
        session_expires_at=principal.session_expires_at,
    )


def hash_algorithm(password_hash: str) -> str:
    """Name the algorithm of a stored hash from its PHC prefix — safe to display."""
    if not isinstance(password_hash, str):
        return "unknown"
    if password_hash.startswith("$argon2id$"):
        return "argon2id"
    if password_hash.startswith("$argon2i$"):
        return "argon2i"
    if password_hash.startswith("$argon2d$"):
        return "argon2d"
    if password_hash.startswith("$2"):
        return "bcrypt"
    return "unknown"
