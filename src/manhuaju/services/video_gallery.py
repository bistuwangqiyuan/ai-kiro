"""Public video gallery — persist and serve user-generated + sample episodes."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class GalleryVideo:
    video_id: str
    project_id: str
    episode_id: str
    title: str
    genre: str
    platform: str
    video_url: str
    cover_url: str
    is_sample: bool
    created_at: str
    local_video: str = ""
    local_cover: str = ""


class VideoGallery:
    """SQLite-backed gallery registry with optional TOS publish."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = db_path
        self._lock = threading.RLock()
        with self._lock:
            con = sqlite3.connect(str(db_path))
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS gallery_videos (
                    video_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    episode_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    genre TEXT NOT NULL DEFAULT 'ancient',
                    platform TEXT NOT NULL DEFAULT 'douyin',
                    video_url TEXT NOT NULL,
                    cover_url TEXT NOT NULL DEFAULT '',
                    is_sample INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    local_video TEXT NOT NULL DEFAULT '',
                    local_cover TEXT NOT NULL DEFAULT ''
                )
                """
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_gallery_project ON gallery_videos(project_id)"
            )
            con.commit()
            con.close()

    def add(self, entry: GalleryVideo) -> GalleryVideo:
        with self._lock:
            con = sqlite3.connect(str(self._db))
            con.execute(
                """
                INSERT OR REPLACE INTO gallery_videos
                (video_id, project_id, episode_id, title, genre, platform,
                 video_url, cover_url, is_sample, created_at, local_video, local_cover)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.video_id,
                    entry.project_id,
                    entry.episode_id,
                    entry.title,
                    entry.genre,
                    entry.platform,
                    entry.video_url,
                    entry.cover_url,
                    1 if entry.is_sample else 0,
                    entry.created_at,
                    entry.local_video,
                    entry.local_cover,
                ),
            )
            con.commit()
            con.close()
        return entry

    def list_videos(
        self,
        *,
        limit: int = 100,
        project_id: str | None = None,
    ) -> list[GalleryVideo]:
        with self._lock:
            con = sqlite3.connect(str(self._db))
            if project_id:
                rows = con.execute(
                    """
                    SELECT video_id, project_id, episode_id, title, genre, platform,
                           video_url, cover_url, is_sample, created_at, local_video, local_cover
                    FROM gallery_videos WHERE project_id = ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (project_id, limit),
                ).fetchall()
            else:
                rows = con.execute(
                    """
                    SELECT video_id, project_id, episode_id, title, genre, platform,
                           video_url, cover_url, is_sample, created_at, local_video, local_cover
                    FROM gallery_videos
                    ORDER BY is_sample DESC, created_at DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            con.close()
        return [_row_to_video(r) for r in rows]

    def get(self, video_id: str) -> GalleryVideo | None:
        with self._lock:
            con = sqlite3.connect(str(self._db))
            row = con.execute(
                """
                SELECT video_id, project_id, episode_id, title, genre, platform,
                       video_url, cover_url, is_sample, created_at, local_video, local_cover
                FROM gallery_videos WHERE video_id = ?
                """,
                (video_id,),
            ).fetchone()
            con.close()
        return _row_to_video(row) if row else None

    def count(self) -> int:
        with self._lock:
            con = sqlite3.connect(str(self._db))
            row = con.execute("SELECT COUNT(*) FROM gallery_videos").fetchone()
            con.close()
        return int(row[0]) if row else 0


def _row_to_video(row: tuple[Any, ...]) -> GalleryVideo:
    return GalleryVideo(
        video_id=row[0],
        project_id=row[1],
        episode_id=row[2],
        title=row[3],
        genre=row[4],
        platform=row[5],
        video_url=row[6],
        cover_url=row[7],
        is_sample=bool(row[8]),
        created_at=row[9],
        local_video=row[10] or "",
        local_cover=row[11] or "",
    )


def resolve_export_path(root: Path, project_id: str, path_str: str) -> Path | None:
    """Map manifest-relative paths to on-disk files under storage root."""
    if not path_str:
        return None
    raw = Path(path_str)
    if raw.is_file():
        return raw
    norm = path_str.replace("\\", "/").lstrip("/")
    if norm.startswith("api_data/"):
        norm = norm[len("api_data/") :]
    name = Path(norm).name
    candidates = [
        root / norm,
        root / project_id / norm,
        root / project_id / project_id / "export" / name,
        root / project_id / "export" / name,
        root / project_id / "output" / "episodes" / name,
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def publish_project_videos(
    *,
    gallery: VideoGallery,
    storage_root: Path,
    project_id: str,
    manifest: dict[str, Any],
    title: str = "",
    genre: str = "ancient",
    tos: Any | None = None,
    media_url_prefix: str = "/media/videos",
) -> list[GalleryVideo]:
    """Upload export MP4s to TOS (if configured) and register in gallery."""
    published: list[GalleryVideo] = []
    exports: list[dict[str, Any]] = manifest.get("exports") or []
    now = datetime.now(UTC).isoformat()

    for block in exports:
        if isinstance(block, dict) and "platforms" in block:
            ep = block.get("episode_id", "ep01")
            for platform, info in block.get("platforms", {}).items():
                published.extend(
                    _publish_one(
                        gallery=gallery,
                        storage_root=storage_root,
                        project_id=project_id,
                        episode_id=ep,
                        platform=platform,
                        mp4_path=info.get("mp4", ""),
                        cover_path=info.get("cover", ""),
                        title=title or f"{project_id} · {ep}",
                        genre=genre,
                        tos=tos,
                        media_url_prefix=media_url_prefix,
                        created_at=now,
                    )
                )
            continue
        for platform, info in block.items():
            if not isinstance(info, dict):
                continue
            ep = info.get("episode_id") or Path(str(info.get("mp4", ""))).stem.split("_")[0]
            published.extend(
                _publish_one(
                    gallery=gallery,
                    storage_root=storage_root,
                    project_id=project_id,
                    episode_id=ep,
                    platform=platform,
                    mp4_path=info.get("mp4", ""),
                    cover_path=info.get("cover", ""),
                    title=title or f"{project_id} · {ep}",
                    genre=genre,
                    tos=tos,
                    media_url_prefix=media_url_prefix,
                    created_at=now,
                )
            )

    if published:
        return published

    for ep in manifest.get("episodes") or []:
        ep_id = ep.get("episode_id", "ep01")
        final_mp4 = ep.get("final_mp4", "")
        mp4 = resolve_export_path(storage_root, project_id, final_mp4)
        if not mp4:
            continue
        published.extend(
            _publish_one(
                gallery=gallery,
                storage_root=storage_root,
                project_id=project_id,
                episode_id=ep_id,
                platform="douyin",
                mp4_path=str(mp4),
                cover_path="",
                title=title or f"{project_id} · {ep_id}",
                genre=genre,
                tos=tos,
                media_url_prefix=media_url_prefix,
                created_at=now,
            )
        )
    return published


def _publish_one(
    *,
    gallery: VideoGallery,
    storage_root: Path,
    project_id: str,
    episode_id: str,
    platform: str,
    mp4_path: str,
    cover_path: str,
    title: str,
    genre: str,
    tos: Any | None,
    media_url_prefix: str,
    created_at: str,
) -> list[GalleryVideo]:
    mp4 = resolve_export_path(storage_root, project_id, mp4_path)
    if not mp4 or not mp4.is_file():
        return []

    cover = resolve_export_path(storage_root, project_id, cover_path) if cover_path else None
    video_id = f"vid_{uuid.uuid4().hex[:12]}"
    tos_key = f"gallery/{project_id}/{episode_id}_{platform}.mp4"
    cover_key = f"gallery/{project_id}/{episode_id}_{platform}_cover.jpg"

    video_url = f"{media_url_prefix}/{video_id}"
    cover_url = ""

    if tos is not None and getattr(tos, "configured", False):
        try:
            up = tos.upload_file(mp4, key=tos_key, content_type="video/mp4")
            video_url = up.public_url
            if cover and cover.is_file():
                cup = tos.upload_file(cover, key=cover_key, content_type="image/jpeg")
                cover_url = cup.public_url
        except Exception:
            pass

    entry = GalleryVideo(
        video_id=video_id,
        project_id=project_id,
        episode_id=episode_id,
        title=title,
        genre=genre,
        platform=platform,
        video_url=video_url,
        cover_url=cover_url,
        is_sample=False,
        created_at=created_at,
        local_video=str(mp4),
        local_cover=str(cover) if cover else "",
    )
    gallery.add(entry)
    return [entry]


def seed_bundled_samples(
    *,
    gallery: VideoGallery,
    web_dir: Path,
    media_url_prefix: str = "/media/videos",
) -> int:
    """Load web/samples/manifest.json into gallery (idempotent by video_id)."""
    manifest_path = web_dir / "samples" / "manifest.json"
    if not manifest_path.is_file():
        return 0
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    added = 0
    for item in data.get("samples", []):
        vid = item["video_id"]
        if gallery.get(vid):
            continue
        video_rel = item["video"]
        cover_rel = item.get("cover", "")
        video_path = web_dir / video_rel
        cover_path = web_dir / cover_rel if cover_rel else None
        if not video_path.is_file():
            continue
        entry = GalleryVideo(
            video_id=vid,
            project_id=item.get("project_id", "sample_pilot"),
            episode_id=item.get("episode_id", "ep01"),
            title=item.get("title", "示例漫剧"),
            genre=item.get("genre", "ancient"),
            platform=item.get("platform", "douyin"),
            video_url=f"{media_url_prefix}/{vid}",
            cover_url=f"/media/covers/{vid}" if cover_path and cover_path.is_file() else "",
            is_sample=True,
            created_at=item.get("created_at", datetime.now(UTC).isoformat()),
            local_video=str(video_path.resolve()),
            local_cover=str(cover_path.resolve()) if cover_path and cover_path.is_file() else "",
        )
        gallery.add(entry)
        added += 1
    return added


def video_to_dict(v: GalleryVideo) -> dict[str, Any]:
    d = asdict(v)
    d["is_sample"] = bool(v.is_sample)
    return d
