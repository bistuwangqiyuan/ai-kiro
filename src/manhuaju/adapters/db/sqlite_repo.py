"""SQLite KV repo (M2 replacement for Postgres state journal)."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class SQLiteRepo:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(path))
        self.con.execute(
            "CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)"
        )
        self.con.commit()

    def set(self, k: str, v: str) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (k, v)
        )
        self.con.commit()

    def get(self, k: str) -> str | None:
        row = self.con.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return None if row is None else row[0]

    def all(self) -> dict[str, str]:
        return {k: v for k, v in self.con.execute("SELECT k, v FROM kv").fetchall()}

    def close(self) -> None:
        self.con.close()
