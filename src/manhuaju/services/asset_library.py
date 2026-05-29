"""Digital-asset library — user-uploaded character templates and other refs.

Stores uploaded reference media (character templates first, plus scene / style /
prop) in Volcengine TOS (with a local mirror for serving + fallback) and keeps
metadata in SQLite. Assets are reusable across projects and selectable at
project-creation time; the selected asset URLs are threaded into the render
pipeline's ``reference_map`` so the video model uses them for consistency.

Design mirrors ``services.video_gallery.VideoGallery`` (SQLite + TOS).
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Asset types the render pipeline understands. ``character`` is the first-class
# type wired into per-shot character references; the others are accepted and
# stored generically and merged into the reference_map under their own keys.
ASSET_TYPES = ("character", "scene", "style", "prop")


@dataclass
class Asset:
    asset_id: str
    owner: str  # "" for anonymous
    asset_type: str
    name: str
    tos_url: str  # http(s) URL the render pipeline can consume (or file:// fallback)
    local_path: str  # local mirror used by /media/assets serving
    content_type: str
    bytes: int
    created_at: str
    ref_key: str = ""  # optional explicit reference_map key (e.g. char id / scene:<loc>)


def asset_to_dict(a: Asset) -> dict[str, Any]:
    d = asdict(a)
    d["media_url"] = f"/media/assets/{a.asset_id}"
    return d


class AssetLibrary:
    """SQLite-backed registry of user-uploaded reference assets."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = db_path
        self._lock = threading.RLock()
        with self._lock:
            con = sqlite3.connect(str(db_path))
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL DEFAULT '',
                    asset_type TEXT NOT NULL DEFAULT 'character',
                    name TEXT NOT NULL DEFAULT '',
                    tos_url TEXT NOT NULL DEFAULT '',
                    local_path TEXT NOT NULL DEFAULT '',
                    content_type TEXT NOT NULL DEFAULT 'image/png',
                    bytes INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    ref_key TEXT NOT NULL DEFAULT ''
                )
                """
            )
            con.execute("CREATE INDEX IF NOT EXISTS idx_assets_owner ON assets(owner)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(asset_type)")
            con.commit()
            con.close()

    @staticmethod
    def new_id() -> str:
        return f"asset_{uuid.uuid4().hex[:16]}"

    def add(self, entry: Asset) -> Asset:
        with self._lock:
            con = sqlite3.connect(str(self._db))
            con.execute(
                """
                INSERT OR REPLACE INTO assets
                (asset_id, owner, asset_type, name, tos_url, local_path,
                 content_type, bytes, created_at, ref_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.asset_id,
                    entry.owner,
                    entry.asset_type,
                    entry.name,
                    entry.tos_url,
                    entry.local_path,
                    entry.content_type,
                    int(entry.bytes),
                    entry.created_at,
                    entry.ref_key,
                ),
            )
            con.commit()
            con.close()
        return entry

    @staticmethod
    def _row_to_asset(row: tuple[Any, ...]) -> Asset:
        return Asset(
            asset_id=row[0],
            owner=row[1],
            asset_type=row[2],
            name=row[3],
            tos_url=row[4],
            local_path=row[5],
            content_type=row[6],
            bytes=int(row[7]),
            created_at=row[8],
            ref_key=row[9],
        )

    _COLS = (
        "asset_id, owner, asset_type, name, tos_url, local_path, "
        "content_type, bytes, created_at, ref_key"
    )

    def get(self, asset_id: str) -> Asset | None:
        with self._lock:
            con = sqlite3.connect(str(self._db))
            row = con.execute(
                f"SELECT {self._COLS} FROM assets WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            con.close()
        return self._row_to_asset(row) if row else None

    def list_assets(
        self,
        *,
        owner: str | None = None,
        asset_type: str | None = None,
        limit: int = 200,
    ) -> list[Asset]:
        """List assets. ``owner=None`` returns all; ``owner=""`` only anonymous."""
        clauses: list[str] = []
        params: list[Any] = []
        if owner is not None:
            clauses.append("owner = ?")
            params.append(owner)
        if asset_type:
            clauses.append("asset_type = ?")
            params.append(asset_type)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with self._lock:
            con = sqlite3.connect(str(self._db))
            rows = con.execute(
                f"SELECT {self._COLS} FROM assets{where} "
                f"ORDER BY created_at DESC LIMIT ?",
                tuple(params),
            ).fetchall()
            con.close()
        return [self._row_to_asset(r) for r in rows]

    def resolve_urls(self, asset_ids: list[str]) -> list[str]:
        """Return the consumable (TOS/http or file) URLs for the given asset ids."""
        out: list[str] = []
        for aid in asset_ids:
            a = self.get(aid)
            if a and a.tos_url:
                out.append(a.tos_url)
        return out

    def delete(self, asset_id: str, *, owner: str | None = None) -> bool:
        """Delete an asset. If ``owner`` is given, only delete if it matches."""
        with self._lock:
            con = sqlite3.connect(str(self._db))
            if owner is None:
                cur = con.execute("DELETE FROM assets WHERE asset_id = ?", (asset_id,))
            else:
                cur = con.execute(
                    "DELETE FROM assets WHERE asset_id = ? AND owner = ?",
                    (asset_id, owner),
                )
            deleted = cur.rowcount > 0
            con.commit()
            con.close()
        return deleted


def make_asset(
    *,
    asset_type: str,
    name: str,
    tos_url: str,
    local_path: str,
    content_type: str,
    size_bytes: int,
    owner: str = "",
    ref_key: str = "",
) -> Asset:
    at = asset_type if asset_type in ASSET_TYPES else "character"
    return Asset(
        asset_id=AssetLibrary.new_id(),
        owner=owner or "",
        asset_type=at,
        name=name or "未命名资产",
        tos_url=tos_url,
        local_path=local_path,
        content_type=content_type or "image/png",
        bytes=int(size_bytes),
        created_at=datetime.now(UTC).isoformat(),
        ref_key=ref_key or "",
    )
