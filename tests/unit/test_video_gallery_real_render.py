"""Gate the real-render-vs-sample fallback logic in the public video gallery."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manhuaju.services.video_gallery import (
    VideoGallery,
    publish_project_videos,
)


def _write_mp4(path: Path, size_bytes: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * size_bytes)
    return path


def _seed_sample_pool(web_dir: Path) -> Path:
    samples = web_dir / "samples"
    videos = samples / "videos"
    videos.mkdir(parents=True, exist_ok=True)
    sample_video = _write_mp4(videos / "sample_ep01.mp4", 5 * 1024 * 1024)
    manifest = {
        "samples": [
            {
                "video_id": "vid_sample_ep01",
                "video": "samples/videos/sample_ep01.mp4",
                "title": "示例 ep01",
                "episode_id": "ep01",
                "is_sample": True,
            }
        ]
    }
    (samples / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return sample_video


@pytest.fixture()
def web_dir(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    _seed_sample_pool(web)
    return web


@pytest.fixture()
def storage(tmp_path: Path) -> Path:
    return tmp_path / "storage"


@pytest.fixture()
def gallery(tmp_path: Path) -> VideoGallery:
    return VideoGallery(tmp_path / "gallery.sqlite")


def _manifest_with_episode(storage_root: Path, project_id: str, mp4: Path) -> dict:
    return {
        "project_id": project_id,
        "episodes": [
            {"episode_id": "ep01", "final_mp4": str(mp4)},
        ],
        "exports": [
            {"episode_id": "ep01", "platforms": {"douyin": {"mp4": str(mp4)}}}
        ],
    }


def test_mock_run_substitutes_sample(
    gallery: VideoGallery, storage: Path, web_dir: Path
) -> None:
    """Mock pipeline (1 s synthetic mp4) → gallery shows curated sample preview."""
    project_id = "proj_mock"
    real_mp4 = _write_mp4(storage / project_id / "output" / "ep01_final.mp4", 30 * 1024)
    manifest = _manifest_with_episode(storage, project_id, real_mp4)

    published = publish_project_videos(
        gallery=gallery,
        storage_root=storage,
        project_id=project_id,
        manifest=manifest,
        web_dir=web_dir,
        prefer_real_render=False,
    )
    assert len(published) == 1
    assert published[0].is_sample is True
    assert "sample_ep01.mp4" in published[0].local_video


def test_live_run_uses_real_render(
    gallery: VideoGallery, storage: Path, web_dir: Path
) -> None:
    """Live/hybrid pipeline → gallery surfaces the real final_mp4 even though a sample exists."""
    project_id = "proj_live"
    real_mp4 = _write_mp4(
        storage / project_id / "output" / "ep01_final.mp4", 6 * 1024 * 1024
    )
    manifest = _manifest_with_episode(storage, project_id, real_mp4)

    published = publish_project_videos(
        gallery=gallery,
        storage_root=storage,
        project_id=project_id,
        manifest=manifest,
        web_dir=web_dir,
        prefer_real_render=True,
    )
    assert len(published) == 1
    assert published[0].is_sample is False
    assert published[0].local_video == str(real_mp4)


def test_live_run_with_missing_render_falls_back_to_sample(
    gallery: VideoGallery, storage: Path, web_dir: Path
) -> None:
    """If real render is missing entirely, surface the sample so gallery isn't empty."""
    project_id = "proj_live_missing"
    manifest = {
        "project_id": project_id,
        "episodes": [{"episode_id": "ep01", "final_mp4": "does/not/exist.mp4"}],
        "exports": [],
    }
    published = publish_project_videos(
        gallery=gallery,
        storage_root=storage,
        project_id=project_id,
        manifest=manifest,
        web_dir=web_dir,
        prefer_real_render=True,
    )
    assert len(published) == 1
    assert published[0].is_sample is True


def test_live_run_with_tiny_render_still_uses_real(
    gallery: VideoGallery, storage: Path, web_dir: Path
) -> None:
    """Tiny but real render → still surface it (don't silently mask with sample)."""
    project_id = "proj_live_tiny"
    real_mp4 = _write_mp4(storage / project_id / "output" / "ep01_final.mp4", 30 * 1024)
    manifest = _manifest_with_episode(storage, project_id, real_mp4)

    published = publish_project_videos(
        gallery=gallery,
        storage_root=storage,
        project_id=project_id,
        manifest=manifest,
        web_dir=web_dir,
        prefer_real_render=True,
    )
    assert len(published) == 1
    assert published[0].is_sample is False
    assert published[0].local_video == str(real_mp4)
