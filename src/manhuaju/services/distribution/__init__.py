"""Platform distribution presets and export helpers (REQ-DIST-001..004)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

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


def transcode_for_platform(in_mp4: Path, out_mp4: Path, platform: str) -> Path:
    preset = PLATFORM_PRESETS.get(platform, PLATFORM_PRESETS["douyin"])
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale={preset['scale']}:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2"
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(in_mp4),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-b:v",
        preset["video_bitrate"],
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_mp4


def apply_watermark(in_mp4: Path, out_mp4: Path, text: str = "@manhuaju") -> Path:
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    safe = text.replace(":", "\\:").replace("'", "\\'")
    vf = f"drawtext=text='{safe}':fontcolor=white@0.7:fontsize=24:x=w-tw-20:y=h-th-20"
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(in_mp4),
        "-vf",
        vf,
        "-c:a",
        "copy",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_mp4


def extract_cover(in_mp4: Path, out_png: Path) -> Path:
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(in_mp4),
        "-vframes",
        "1",
        str(out_png),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_png


def write_copy_pack(out_path: Path, *, title: str, synopsis: str, hooks: list[str]) -> Path:
    pack = {
        "title": title,
        "synopsis": synopsis,
        "hooks": hooks,
        "hashtags": ["#AI漫剧", "#竖屏短剧"],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
