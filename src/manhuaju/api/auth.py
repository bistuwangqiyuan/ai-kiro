"""Optional username/password auth for the live user portal.

Design choices (see plan add-auth-loop-deploy):

- "Username" is treated as an opaque, case-insensitive email-format string.
  Validation is regex-lite + length bounds; we never send mail.
- Password hashing uses ``hashlib.scrypt`` (Python stdlib) with a random
  per-user salt. Format: ``scrypt$<salt_hex>$<hash_hex>``.
- Sessions are opaque tokens (``secrets.token_urlsafe(32)``) stored in the same
  SQLite DB with a TTL (default 30 days). They are sent as
  ``Authorization: Bearer <token>``.
- ``current_user_optional`` is a FastAPI dependency that returns a user dict
  when a valid bearer token is present, or ``None`` otherwise. Public endpoints
  remain accessible to anonymous traffic.

The store is intentionally tiny (no SQLAlchemy / passlib / python-jose / bcrypt
dependencies) so the existing image / requirements stack stays untouched.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from fastapi import Header, HTTPException

DEFAULT_TTL_S = 30 * 24 * 3600

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64

_USERNAME_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def _validate_username(username: str) -> str:
    norm = _normalize_username(username)
    if not (5 <= len(norm) <= 128):
        raise ValueError("invalid_username")
    if not _USERNAME_RE.match(norm):
        raise ValueError("invalid_username")
    return norm


def _validate_password(password: str) -> str:
    if not isinstance(password, str):
        raise ValueError("invalid_password")
    if not (6 <= len(password) <= 128):
        raise ValueError("invalid_password")
    return password


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, hash_hex = stored.split("$", 2)
    except ValueError:
        return False
    if algo != "scrypt":
        return False
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=len(expected),
    )
    return hmac.compare_digest(derived, expected)


@dataclass
class User:
    username: str
    created_at: int

    def to_public(self) -> dict[str, object]:
        return {"username": self.username, "created_at": self.created_at}


@dataclass
class Session:
    token: str
    username: str
    expires_at: int
    user: User | None = field(default=None)


class UserStore:
    """Tiny SQLite-backed user + session store."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.RLock()
        with self._lock:
            self._con.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            self._con.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    expires_at INTEGER NOT NULL
                )
                """
            )
            self._con.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_username ON sessions(username)"
            )
            self._con.commit()

    # ---------- users ----------
    def get_user(self, username: str) -> User | None:
        norm = _normalize_username(username)
        with self._lock:
            row = self._con.execute(
                "SELECT username, created_at FROM users WHERE username=?",
                (norm,),
            ).fetchone()
        if not row:
            return None
        return User(username=row[0], created_at=int(row[1]))

    def register(self, username: str, password: str) -> User:
        norm = _validate_username(username)
        _validate_password(password)
        ph = hash_password(password)
        now = int(time.time())
        with self._lock:
            existing = self._con.execute(
                "SELECT 1 FROM users WHERE username=?", (norm,)
            ).fetchone()
            if existing:
                raise ValueError("user_exists")
            self._con.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (norm, ph, now),
            )
            self._con.commit()
        return User(username=norm, created_at=now)

    def verify_credentials(self, username: str, password: str) -> User:
        norm = _normalize_username(username)
        with self._lock:
            row = self._con.execute(
                "SELECT username, password_hash, created_at FROM users WHERE username=?",
                (norm,),
            ).fetchone()
        if not row:
            raise ValueError("invalid_credentials")
        if not verify_password(password, row[1]):
            raise ValueError("invalid_credentials")
        return User(username=row[0], created_at=int(row[2]))

    # ---------- sessions ----------
    def create_session(self, username: str, *, ttl_s: int = DEFAULT_TTL_S) -> Session:
        norm = _normalize_username(username)
        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + int(ttl_s)
        with self._lock:
            self._con.execute(
                "INSERT INTO sessions (token, username, expires_at) VALUES (?, ?, ?)",
                (token, norm, expires_at),
            )
            self._con.commit()
        return Session(token=token, username=norm, expires_at=expires_at)

    def resolve_session(self, token: str) -> Session | None:
        if not token:
            return None
        now = int(time.time())
        with self._lock:
            row = self._con.execute(
                "SELECT token, username, expires_at FROM sessions WHERE token=?",
                (token,),
            ).fetchone()
            if not row:
                return None
            if int(row[2]) < now:
                # Expired — clean up lazily.
                self._con.execute("DELETE FROM sessions WHERE token=?", (token,))
                self._con.commit()
                return None
            user_row = self._con.execute(
                "SELECT username, created_at FROM users WHERE username=?",
                (row[1],),
            ).fetchone()
        if not user_row:
            return None
        return Session(
            token=row[0],
            username=row[1],
            expires_at=int(row[2]),
            user=User(username=user_row[0], created_at=int(user_row[1])),
        )

    def delete_session(self, token: str) -> None:
        if not token:
            return
        with self._lock:
            self._con.execute("DELETE FROM sessions WHERE token=?", (token,))
            self._con.commit()

    def purge_expired(self) -> int:
        now = int(time.time())
        with self._lock:
            cur = self._con.execute("DELETE FROM sessions WHERE expires_at<?", (now,))
            self._con.commit()
            return cur.rowcount or 0

    def count_users(self) -> int:
        with self._lock:
            row = self._con.execute("SELECT COUNT(*) FROM users").fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        with self._lock:
            self._con.close()


# ---------- seed ----------
DEFAULT_TEST_USERS: tuple[tuple[str, str], ...] = (
    ("test1@139.com", "123456"),
    ("test2@139.com", "123456"),
)


def seed_default_users(
    store: UserStore,
    pairs: Iterable[tuple[str, str]] = DEFAULT_TEST_USERS,
) -> list[str]:
    """Idempotently seed test accounts. Returns the usernames newly created."""
    created: list[str] = []
    for username, password in pairs:
        try:
            norm = _normalize_username(username)
            if store.get_user(norm) is None:
                store.register(norm, password)
                created.append(norm)
        except ValueError:
            continue
    return created


# ---------- FastAPI dependency factories ----------
def extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer":
        return None
    return token.strip() or None


def make_current_user_optional(store: UserStore):
    """Return a dependency that yields a user dict if authenticated, else None."""

    def _dep(authorization: str | None = Header(default=None)) -> dict[str, object] | None:
        token = extract_bearer(authorization)
        if not token:
            return None
        sess = store.resolve_session(token)
        if not sess or not sess.user:
            return None
        return {**sess.user.to_public(), "token": sess.token}

    return _dep


def make_current_user_required(store: UserStore):
    """Return a dependency that raises 401 if no valid bearer token is supplied."""

    def _dep(authorization: str | None = Header(default=None)) -> dict[str, object]:
        token = extract_bearer(authorization)
        if not token:
            raise HTTPException(status_code=401, detail="missing_bearer")
        sess = store.resolve_session(token)
        if not sess or not sess.user:
            raise HTTPException(status_code=401, detail="invalid_token")
        return {**sess.user.to_public(), "token": sess.token}

    return _dep


__all__ = [
    "DEFAULT_TEST_USERS",
    "Session",
    "User",
    "UserStore",
    "extract_bearer",
    "hash_password",
    "make_current_user_optional",
    "make_current_user_required",
    "seed_default_users",
    "verify_password",
]
