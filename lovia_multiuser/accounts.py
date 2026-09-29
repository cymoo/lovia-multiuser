"""The user directory: who exists, who is an admin, who is disabled.

:class:`Directory` is the seam the app depends on. :class:`Accounts` is the
reference implementation — SQLite with scrypt password hashes — meant to be
replaced by your own user system (LDAP, the business DB, an IdP's API).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# User ids appear in URLs (/u/<id>/) and directory names (users/<id>/), so they
# are restricted to a slug; display names are free-form.
USER_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")


@dataclass(frozen=True)
class User:
    id: str
    name: str
    admin: bool = False
    disabled: bool = False


class Directory(Protocol):
    """What the app needs to know about users. Looked up on every request,
    so a change (disable, role) takes effect immediately."""

    async def get(self, user_id: str) -> User | None: ...
    async def list(self) -> list[User]: ...
    async def set_disabled(self, user_id: str, disabled: bool) -> None: ...


def valid_user_id(user_id: str) -> bool:
    return USER_ID.fullmatch(user_id) is not None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    _, salt, digest = stored.split("$")
    got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
    return hmac.compare_digest(got.hex(), digest)


# Verified against when the user doesn't exist, so a login attempt takes the
# same time either way and doesn't reveal which ids are registered.
_DUMMY_HASH = hash_password(secrets.token_hex(8))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    admin INTEGER NOT NULL DEFAULT 0,
    disabled INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
"""


class Accounts:
    """Reference :class:`Directory` on SQLite, plus password sign-in."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _get(self, user_id: str) -> tuple[User, str] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, name, admin, disabled, password_hash FROM users "
                "WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return User(row[0], row[1], bool(row[2]), bool(row[3])), row[4]

    # ---- Directory ---------------------------------------------------------

    async def get(self, user_id: str) -> User | None:
        found = await asyncio.to_thread(self._get, user_id)
        return found[0] if found else None

    async def list(self) -> list[User]:
        def _impl() -> list[User]:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT id, name, admin, disabled FROM users ORDER BY id"
                ).fetchall()
            return [User(r[0], r[1], bool(r[2]), bool(r[3])) for r in rows]

        return await asyncio.to_thread(_impl)

    async def set_disabled(self, user_id: str, disabled: bool) -> None:
        await asyncio.to_thread(self._update, "disabled = ?", (int(disabled),), user_id)

    # ---- management (CLI) and sign-in ---------------------------------------

    async def add(
        self,
        user_id: str,
        password: str,
        *,
        name: str | None = None,
        admin: bool = False,
    ) -> User:
        if not valid_user_id(user_id):
            raise ValueError(
                f"invalid user id {user_id!r}: use 1-32 of a-z, 0-9, '_' or '-'"
            )
        user = User(user_id, name or user_id, admin)

        def _impl() -> None:
            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO users (id, name, password_hash, admin, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        user.id,
                        user.name,
                        hash_password(password),
                        int(admin),
                        time.time(),
                    ),
                )

        try:
            await asyncio.to_thread(_impl)
        except sqlite3.IntegrityError:
            raise ValueError(f"user {user_id!r} already exists") from None
        return user

    async def set_password(self, user_id: str, password: str) -> None:
        await asyncio.to_thread(
            self._update, "password_hash = ?", (hash_password(password),), user_id
        )

    async def set_admin(self, user_id: str, admin: bool) -> None:
        await asyncio.to_thread(self._update, "admin = ?", (int(admin),), user_id)

    async def verify(self, user_id: str, password: str) -> User | None:
        """The user if ``password`` is theirs — disabled accounts included;
        the caller decides what a disabled account may do."""
        found = await asyncio.to_thread(self._get, user_id)
        stored = found[1] if found else _DUMMY_HASH
        ok = await asyncio.to_thread(check_password, password, stored)
        return found[0] if found and ok else None

    def _update(
        self, assignment: str, params: tuple[object, ...], user_id: str
    ) -> None:
        with self._conn() as conn:
            cur = conn.execute(
                f"UPDATE users SET {assignment} WHERE id = ?", (*params, user_id)
            )
        if cur.rowcount == 0:
            raise KeyError(f"no such user: {user_id!r}")
