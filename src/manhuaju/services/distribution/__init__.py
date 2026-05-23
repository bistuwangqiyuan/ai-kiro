"""Distribution helpers — ffmpeg transcoding + cover extraction + copy pack writing (v4).

Backed by ``config/distribution-platforms.yaml`` specs. The legacy hard-coded
``PLATFORM_PRESETS`` table is preserved for backward compatibility, but
``platform_spec()`` should be preferred in new code.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from manhuaju.utils.paths import config_dir

_PLATFORM_CACHE: dict[str, Any] | None = None


PLATFORM_PRESETS: dict[str, dict[str, Any]] = {
    "douyin": {
        "aspect": "9:16",
        "max_duration_s": 180,
        "video_bitrate": "4M",
        "scale": "1080:1920",
    },
    "kuaishou": {
        "aspect": "9:16",
        "max_duration_s": 180,
        "video_bitrate": "3.5M",
        "scale": "1080:1920",
    },
    "weixin": {
        "aspect": "9:16",
        "max_duration_s": 300,
        "video_bitrate": "4M",
        "scale": "1080:1920",
    },
}


def _load_platforms() -> dict[str, Any]:
    global _PLATFORM_CACHE  # noqa: PLW0603
    if _PLATFORM_CACHE is not None:
        return _PLATFORM_CACHE
    path = config_dir() / "distribution-platforms.yaml"
    if not path.exists():
        _PLATFORM_CACHE = {}
        return _PLATFORM_CACHE
    try:
        _PLATFORM_CACHE = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        _PLATFORM_CACHE = {}
    return _PLATFORM_CACHE


def platform_spec(platform: str) -> dict[str, Any]:
    return (_load_platforms().get("platforms") or {}).get(platform, {})


def transcode_for_platform(
    src: str | Path,
    dst: str | Path,
    platform: str,
) -> Path:
    """Transcode the source mp4 to the platform's spec; falls back to plain copy."""
    src_p = Path(src)
    dst_p = Path(dst)
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    if not src_p.exists():
        raise FileNotFoundError(f"distribution source missing: {src_p}")

    spec = platform_spec(platform)
    if not shutil.which("ffmpeg") or not spec:
        shutil.copy2(src_p, dst_p)
        return dst_p

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(src_p),
        "-c:v", str(spec.get("video_codec", "libx264")),
        "-preset", "medium",
        "-profile:v", str(spec.get("profile", "high")),
        "-pix_fmt", str(spec.get("pixel_format", "yuv420p")),
        "-b:v", str(spec.get("video_bitrate", "5000k")),
        "-maxrate", str(spec.get("max_bitrate", "8000k")),
        "-bufsize", str(spec.get("bufsize", "10000k")),
        "-r", str(spec.get("fps", 30)),
        "-c:a", str(spec.get("audio_codec", "aac")),
        "-b:a", str(spec.get("audio_bitrate", "192k")),
        "-ar", str(spec.get("audio_sample_rate", 48000)),
        "-ac", str(spec.get("audio_channels", 2)),
        "-movflags", "+faststart",
        str(dst_p),
    ]
    primary = str(spec.get("primary_resolution", "")).lower().replace("x", ":")
    if primary and ":" in primary:
        w, h = primary.split(":")
        cmd.insert(-1, "-vf")
        cmd.insert(-1, f"scale={w}:{h}:flags=lanczos,setsar=1")
    try:
        subprocess.run(cmd, check=False, timeout=600, capture_output=True)
    except (subprocess.SubprocessError, OSError):
        shutil.copy2(src_p, dst_p)
        return dst_p
    if not dst_p.exists() or dst_p.stat().st_size == 0:
        shutil.copy2(src_p, dst_p)
    return dst_p


def extract_cover(src: str | Path, dst: str | Path, *, at_s: float = 0.5) -> Path:
    src_p = Path(src)
    dst_p = Path(dst)
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    if not src_p.exists() or not shutil.which("ffmpeg"):
        try:
            from PIL import Image

            Image.new("RGB", (1080, 1440), (32, 32, 64)).save(dst_p, "PNG")
        except Exception:
            dst_p.write_bytes(b"")
        return dst_p
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-ss", f"{at_s:.2f}",
        "-i", str(src_p),
        "-frames:v", "1",
        "-q:v", "2",
        str(dst_p),
    ]
    try:
        subprocess.run(cmd, check=False, timeout=30, capture_output=True)
    except (subprocess.SubprocessError, OSError):
        pass
    if not dst_p.exists() or dst_p.stat().st_size == 0:
        try:
            from PIL import Image

            Image.new("RGB", (1080, 1440), (32, 32, 64)).save(dst_p, "PNG")
        except Exception:
            dst_p.write_bytes(b"")
    return dst_p


def apply_watermark(src: str | Path, dst: str | Path, *, text: str = "MANHUAJU AI") -> Path:
    src_p = Path(src)
    dst_p = Path(dst)
    dst_p.parent.mkdir(parents=True, exist_ok=True)
    if not shutil.which("ffmpeg") or not src_p.exists():
        if src_p.exists():
            shutil.copy2(src_p, dst_p)
        else:
            dst_p.write_bytes(b"")
        return dst_p
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-i", str(src_p),
        "-vf",
        f"drawtext=text='{text}':fontcolor=white@0.85:fontsize=28:x=w-tw-30:y=h-th-30:"
        "borderw=2:bordercolor=black@0.6",
        "-c:a", "copy",
        str(dst_p),
    ]
    try:
        subprocess.run(cmd, check=False, timeout=300, capture_output=True)
    except (subprocess.SubprocessError, OSError):
        shutil.copy2(src_p, dst_p)
    if not dst_p.exists() or dst_p.stat().st_size == 0:
        shutil.copy2(src_p, dst_p)
    return dst_p


def write_copy_pack(
    out_path: str | Path,
    *,
    title: str,
    synopsis: str,
    hooks: list[str] | None = None,
    tags: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    pack: dict[str, Any] = {
        "title": title,
        "synopsis": synopsis,
        "hooks": hooks or [],
        "tags": tags or [],
        **(extra or {}),
    }
    if "hashtags" not in pack:
        pack["hashtags"] = ["#AI漫剧", "#竖屏短剧"]
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
