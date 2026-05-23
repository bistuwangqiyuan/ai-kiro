"""SQLite KV repo (M2 replacement for Postgres state journal)."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class SQLiteRepo:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Allow shared use across FastAPI's threadpool workers; pair every
        # write with an explicit lock so we keep ACID semantics intact.
        self.con = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.RLock()
        with self._lock:
            self.con.execute(
                "CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)"
            )
            self.con.commit()

    def set(self, k: str, v: str) -> None:
        with self._lock:
            self.con.execute(
                "INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (k, v)
            )
            self.con.commit()

    def get(self, k: str) -> str | None:
        with self._lock:
            row = self.con.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return None if row is None else row[0]

    def all(self) -> dict[str, str]:
        with self._lock:
            rows = self.con.execute("SELECT k, v FROM kv").fetchall()
        return {k: v for k, v in rows}

    def scan(self, prefix: str) -> list[str]:
        """Return keys starting with ``prefix`` (LIKE 'prefix%')."""
        with self._lock:
            rows = self.con.execute(
                "SELECT k FROM kv WHERE k LIKE ? ORDER BY k DESC", (f"{prefix}%",)
            ).fetchall()
        return [r[0] for r in rows]

    def close(self) -> None:
        with self._lock:
            self.con.close()
