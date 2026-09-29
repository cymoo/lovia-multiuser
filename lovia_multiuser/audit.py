"""Audit log: who touched whose data, and what admins changed.

Two kinds of entries share one table:

* ``http`` — a request into another user's space (``actor != owner``): an
  admin viewing, a denied write, a user probing someone else's id. A user
  working in their own space is not audited.
* ``user.*`` — admin actions on accounts (``user.disable``, ``user.enable``).
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    actor TEXT NOT NULL,
    owner TEXT,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    status INTEGER
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_owner ON audit_log(owner, ts DESC);
"""


@dataclass(frozen=True)
class AuditEntry:
    ts: float
    actor: str
    owner: str | None
    action: str
    detail: str
    status: int | None


class AuditLog:
    """Append-only audit trail on SQLite."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)

    def _execute(self, sql: str, params: tuple[object, ...]) -> list[tuple]:
        conn = sqlite3.connect(self.path)
        try:
            with conn:
                return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    async def record(
        self,
        actor: str,
        action: str,
        *,
        owner: str | None = None,
        detail: str = "",
        status: int | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._execute,
            "INSERT INTO audit_log (ts, actor, owner, action, detail, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), actor, owner, action, detail, status),
        )

    async def recent(
        self,
        *,
        actor: str | None = None,
        owner: str | None = None,
        limit: int = 200,
    ) -> list[AuditEntry]:
        where, params = [], []
        if actor:
            where.append("actor = ?")
            params.append(actor)
        if owner:
            where.append("owner = ?")
            params.append(owner)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        rows = await asyncio.to_thread(
            self._execute,
            "SELECT ts, actor, owner, action, detail, status FROM audit_log "
            f"{clause} ORDER BY ts DESC, id DESC LIMIT ?",
            (*params, limit),
        )
        return [AuditEntry(*row) for row in rows]
