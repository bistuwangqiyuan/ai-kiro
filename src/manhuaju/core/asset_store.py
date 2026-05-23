"""Persistent stores for character & scene assets (v4).

docx 三/四节「人设固化」「场景复用」依赖：

- ``CharacterAssetStore`` — `(char_id, outfit_id)` → 14 张参考图 URL；全集复用。
  实现 tech.md 跨集一致性「防线 2」铁律。
- ``SceneAssetCache`` — `(genre, loc_id, time_of_day, weather)` → 6 张场景图 URL；
  跨项目复用，降低重复生成成本。
- ``VersionStore`` — 任意 artefact 版本记录（用于 docx 十二节「版本管理」回滚）。

后端：默认 SQLite（单机/开发）；生产可换 Postgres（实现同接口即可）。
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CharacterAssetRecord:
    char_id: str
    outfit_id: str
    project_id: str
    local_paths: list[str] = field(default_factory=list)
    public_urls: list[str] = field(default_factory=list)
    provider: str = "mock"
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SceneAssetRecord:
    cache_key: str
    local_paths: list[str] = field(default_factory=list)
    public_urls: list[str] = field(default_factory=list)
    provider: str = "mock"
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class _SQLiteBase:
    def __init__(self, db_path: str | Path) -> None:
        self._lock = threading.Lock()
        self._path = str(db_path)
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def _init_schema(self) -> None:  # pragma: no cover — overridden
        raise NotImplementedError


class CharacterAssetStore(_SQLiteBase):
    """Per-character reference library — single source of truth across episodes."""

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS manhuaju_character_assets (
                    char_id TEXT NOT NULL,
                    outfit_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    local_paths TEXT NOT NULL,
                    public_urls TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    metadata TEXT NOT NULL,
                    PRIMARY KEY (project_id, char_id, outfit_id)
                )"""
            )

    def put(self, record: CharacterAssetRecord) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO manhuaju_character_assets
                   (char_id, outfit_id, project_id, local_paths, public_urls,
                    provider, created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.char_id,
                    record.outfit_id,
                    record.project_id,
                    json.dumps(record.local_paths, ensure_ascii=False),
                    json.dumps(record.public_urls, ensure_ascii=False),
                    record.provider,
                    record.created_at,
                    json.dumps(record.metadata, ensure_ascii=False),
                ),
            )

    def get(self, project_id: str, char_id: str, outfit_id: str) -> CharacterAssetRecord | None:
        with self._conn() as c:
            row = c.execute(
                """SELECT char_id, outfit_id, project_id, local_paths, public_urls,
                          provider, created_at, metadata
                   FROM manhuaju_character_assets
                   WHERE project_id = ? AND char_id = ? AND outfit_id = ?""",
                (project_id, char_id, outfit_id),
            ).fetchone()
        if not row:
            return None
        return CharacterAssetRecord(
            char_id=row[0],
            outfit_id=row[1],
            project_id=row[2],
            local_paths=json.loads(row[3]),
            public_urls=json.loads(row[4]),
            provider=row[5],
            created_at=row[6],
            metadata=json.loads(row[7]),
        )

    def list_by_project(self, project_id: str) -> list[CharacterAssetRecord]:
        with self._conn() as c:
            rows = c.execute(
                """SELECT char_id, outfit_id, project_id, local_paths, public_urls,
                          provider, created_at, metadata
                   FROM manhuaju_character_assets WHERE project_id = ?""",
                (project_id,),
            ).fetchall()
        return [
            CharacterAssetRecord(
                char_id=r[0],
                outfit_id=r[1],
                project_id=r[2],
                local_paths=json.loads(r[3]),
                public_urls=json.loads(r[4]),
                provider=r[5],
                created_at=r[6],
                metadata=json.loads(r[7]),
            )
            for r in rows
        ]


class SceneAssetCache(_SQLiteBase):
    """(genre, loc_id, time_of_day, weather) → 6 张场景图 URL — 全局复用。"""

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS manhuaju_scene_assets (
                    cache_key TEXT PRIMARY KEY,
                    local_paths TEXT NOT NULL,
                    public_urls TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    metadata TEXT NOT NULL
                )"""
            )

    def lookup(self, key: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT local_paths, public_urls, provider, metadata "
                "FROM manhuaju_scene_assets WHERE cache_key = ?",
                (key,),
            ).fetchone()
        if not row:
            return None
        return {
            "local_paths": json.loads(row[0]),
            "public_urls": json.loads(row[1]),
            "provider": row[2],
            "metadata": json.loads(row[3]),
        }

    def store(self, key: str, payload: dict[str, Any]) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO manhuaju_scene_assets
                   (cache_key, local_paths, public_urls, provider, created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    key,
                    json.dumps(payload.get("local_paths", []), ensure_ascii=False),
                    json.dumps(payload.get("public_urls", []), ensure_ascii=False),
                    payload.get("provider", "unknown"),
                    time.time(),
                    json.dumps(payload.get("metadata", {}), ensure_ascii=False),
                ),
            )


class VersionStore(_SQLiteBase):
    """通用工件版本记录 — docx 十二节「版本管理」回滚 / 对比 / 追溯。"""

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS manhuaju_versions (
                    version_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    artefact_kind TEXT NOT NULL,
                    artefact_uri TEXT NOT NULL,
                    parent_version_id TEXT,
                    params TEXT NOT NULL,
                    eval_scores TEXT NOT NULL,
                    notes TEXT NOT NULL,
                    created_at REAL NOT NULL
                )"""
            )

    def record(
        self,
        *,
        version_id: str,
        project_id: str,
        artefact_kind: str,
        artefact_uri: str,
        params: dict[str, Any],
        eval_scores: dict[str, Any] | None = None,
        parent_version_id: str | None = None,
        notes: str = "",
    ) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO manhuaju_versions
                   (version_id, project_id, artefact_kind, artefact_uri,
                    parent_version_id, params, eval_scores, notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    version_id,
                    project_id,
                    artefact_kind,
                    artefact_uri,
                    parent_version_id,
                    json.dumps(params, ensure_ascii=False),
                    json.dumps(eval_scores or {}, ensure_ascii=False),
                    notes,
                    time.time(),
                ),
            )

    def list_by_project(self, project_id: str) -> list[dict[str, Any]]:
        with self._conn() as c:
            cur = c.execute(
                "SELECT * FROM manhuaju_versions WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
        if not rows:
            return []
        out = []
        for row in rows:
            rec = dict(zip(cols, row, strict=False))
            for k in ("params", "eval_scores"):
                if isinstance(rec.get(k), str):
                    rec[k] = json.loads(rec[k])
            out.append(rec)
        return out

    def get(self, version_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            cur = c.execute(
                "SELECT * FROM manhuaju_versions WHERE version_id = ?",
                (version_id,),
            )
            row = cur.fetchone()
            cols = [d[0] for d in cur.description] if cur.description else []
        if not row:
            return None
        rec = dict(zip(cols, row, strict=False))
        for k in ("params", "eval_scores"):
            if isinstance(rec.get(k), str):
                rec[k] = json.loads(rec[k])
        return rec


__all__ = [
    "CharacterAssetRecord",
    "CharacterAssetStore",
    "SceneAssetCache",
    "SceneAssetRecord",
    "VersionStore",
    "asdict",  # convenience re-export
]
