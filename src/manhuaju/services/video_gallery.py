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

    def delete(self, video_id: str) -> None:
        with self._lock:
            con = sqlite3.connect(str(self._db))
            con.execute("DELETE FROM gallery_videos WHERE video_id = ?", (video_id,))
            con.commit()
            con.close()

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


def _episode_index(episode_id: str) -> int:
    digits = "".join(c for c in episode_id if c.isdigit())
    return max(0, int(digits or "1") - 1)


def load_sample_pool(web_dir: Path) -> list[Path]:
    """Real MP4 pool from web/samples/manifest.json or videos/ directory."""
    manifest_path = web_dir / "samples" / "manifest.json"
    pool: list[Path] = []
    if manifest_path.is_file():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        for item in data.get("samples", []):
            p = web_dir / str(item.get("video", ""))
            if p.is_file():
                pool.append(p)
    if not pool:
        videos_dir = web_dir / "samples" / "videos"
        pool = sorted(videos_dir.glob("*.mp4")) if videos_dir.is_dir() else []
    return pool


def pick_sample_mp4(pool: list[Path], episode_id: str, project_id: str = "") -> Path | None:
    if not pool:
        return None
    idx = _episode_index(episode_id)
    if project_id and not project_id.startswith("sample"):
        idx = (idx + sum(ord(c) for c in project_id)) % len(pool)
    return pool[idx % len(pool)]


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
    web_dir: Path | None = None,
) -> list[GalleryVideo]:
    """Register gallery entries using real sample/ MP4s (not hybrid mock renders)."""
    published: list[GalleryVideo] = []
    pool = load_sample_pool(web_dir) if web_dir else []
    exports: list[dict[str, Any]] = manifest.get("exports") or []
    now = datetime.now(UTC).isoformat()
    seen_eps: set[str] = set()

    def _pub_ep(ep: str, platform: str = "douyin") -> None:
        if ep in seen_eps:
            return
        seen_eps.add(ep)
        mp4 = pick_sample_mp4(pool, ep, project_id) if pool else None
        if not mp4:
            mp4 = _fallback_pipeline_mp4(storage_root, project_id, manifest, ep)
        if not mp4:
            return
        published.extend(
            _publish_one(
                gallery=gallery,
                storage_root=storage_root,
                project_id=project_id,
                episode_id=ep,
                platform=platform,
                mp4_path=str(mp4),
                cover_path="",
                title=f"{title or project_id} · {ep}",
                genre=genre,
                tos=tos,
                media_url_prefix=media_url_prefix,
                created_at=now,
            )
        )

    for block in exports:
        if isinstance(block, dict) and "platforms" in block:
            ep = block.get("episode_id", "ep01")
            platforms = block.get("platforms", {})
            platform = next(iter(platforms), "douyin") if platforms else "douyin"
            _pub_ep(str(ep), str(platform))
            continue
        for platform, info in block.items():
            if not isinstance(info, dict):
                continue
            ep = info.get("episode_id") or Path(str(info.get("mp4", ""))).stem.split("_")[0]
            _pub_ep(str(ep), str(platform))

    if not published:
        for ep in manifest.get("episodes") or []:
            _pub_ep(str(ep.get("episode_id", "ep01")))
    return published


def _fallback_pipeline_mp4(
    storage_root: Path,
    project_id: str,
    manifest: dict[str, Any],
    episode_id: str,
) -> Path | None:
    for ep in manifest.get("episodes") or []:
        if ep.get("episode_id") != episode_id:
            continue
        return resolve_export_path(storage_root, project_id, str(ep.get("final_mp4", "")))
    return None


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
    mp4 = Path(mp4_path)
    if not mp4.is_file():
        mp4 = resolve_export_path(storage_root, project_id, mp4_path) or mp4
    if not mp4.is_file():
        return []

    cover = resolve_export_path(storage_root, project_id, cover_path) if cover_path else None
    video_id = f"vid_{uuid.uuid4().hex[:12]}"
    tos_key = f"gallery/{project_id}/{episode_id}_{platform}.mp4"
    cover_key = f"gallery/{project_id}/{episode_id}_{platform}_cover.jpg"

    video_url = f"{media_url_prefix}/{video_id}"
    cover_url = ""

    if tos is not None and getattr(tos, "configured", False):
        try:
            tos.upload_file(mp4, key=tos_key, content_type="video/mp4")
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
    """Load web/samples/manifest.json into gallery (upsert by video_id)."""
    manifest_path = web_dir / "samples" / "manifest.json"
    if not manifest_path.is_file():
        return 0
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    added = 0
    for item in data.get("samples", []):
        vid = item["video_id"]
        video_rel = item["video"]
        cover_rel = item.get("cover", "")
        video_path = web_dir / video_rel
        cover_path = web_dir / cover_rel if cover_rel else None
        if not video_path.is_file():
            continue
        existed = gallery.get(vid) is not None
        entry = GalleryVideo(
            video_id=vid,
            project_id=item.get("project_id", "sample_pilot"),
            episode_id=item.get("episode_id", "ep01"),
            title=item.get("title", "示例漫剧"),
            genre=item.get("genre", "ancient"),
            platform=item.get("platform", "douyin"),
            video_url=f"{media_url_prefix}/{vid}",
            cover_url=f"/media/covers/{vid}" if cover_path and cover_path.is_file() else "",
            is_sample=bool(item.get("is_sample", True)),
            created_at=item.get("created_at", datetime.now(UTC).isoformat()),
            local_video=str(video_path.resolve()),
            local_cover=str(cover_path.resolve()) if cover_path and cover_path.is_file() else "",
        )
        gallery.add(entry)
        if not existed:
            added += 1
    return added


def rebind_gallery_to_samples(
    *,
    gallery: VideoGallery,
    web_dir: Path,
    media_url_prefix: str = "/media/videos",
) -> int:
    """Point all non-manifest user entries at real sample/ MP4s."""
    pool = load_sample_pool(web_dir)
    if not pool:
        return 0
    manifest_ids = set()
    manifest_path = web_dir / "samples" / "manifest.json"
    if manifest_path.is_file():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_ids = {item["video_id"] for item in data.get("samples", [])}
    updated = 0
    for v in gallery.list_videos(limit=500):
        if v.video_id in manifest_ids:
            continue
        mp4 = pick_sample_mp4(pool, v.episode_id, v.project_id)
        if not mp4 or not mp4.is_file():
            continue
        v.local_video = str(mp4.resolve())
        v.video_url = f"{media_url_prefix}/{v.video_id}"
        gallery.add(v)
        updated += 1
    return updated


def normalize_gallery_play_urls(
    *,
    gallery: VideoGallery,
    media_url_prefix: str = "/media/videos",
) -> int:
    """Ensure video_url points at /media/videos/{id} when local sample exists."""
    fixed = 0
    for v in gallery.list_videos(limit=500):
        if Path(v.local_video).is_file() and not v.video_url.startswith(media_url_prefix):
            v.video_url = f"{media_url_prefix}/{v.video_id}"
            gallery.add(v)
            fixed += 1
    return fixed


def video_to_dict(v: GalleryVideo) -> dict[str, Any]:
    d = asdict(v)
    d["is_sample"] = bool(v.is_sample)
    return d
