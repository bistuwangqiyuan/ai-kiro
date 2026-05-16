"""ffmpeg + Pillow renderer used by Mock Xiaoyunque/Seedance adapters.

Goal: produce a *real* H.264 mp4 from deterministic Pillow-rendered frames.

Design constraints:
- Deterministic outputs given same `(seed, char_id, outfit_id, location_id,
  mood, key_action, target_seconds, fps)`.
- Per-character "stable palette" so cross-episode same character renders
  identical face/outfit colours -> ArcFace mock cosine ≥ 0.94.
- Frame contains: gradient background + character silhouette circle (face
  colour) + outfit rectangle (outfit palette) + key-action caption + tiny
  STYLE_SHA watermark. This gives a meaningful pHash for pixel-determinism.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Resolution presets (REQ-RO-006)
RESOLUTION_TABLE = {
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "2k": (2560, 1440),
}


def _det_int(*parts: object) -> int:
    s = "|".join(str(p) for p in parts)
    return int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:4], "big")


def _det_color(*parts: object) -> tuple[int, int, int]:
    n = _det_int(*parts)
    return ((n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF)


def stable_face_palette(char_id: str) -> list[tuple[int, int, int]]:
    """Two-colour face palette anchored on char_id only (cross-episode lock)."""
    return [
        _det_color("face", char_id, 0),
        _det_color("face", char_id, 1),
    ]


def stable_outfit_palette(char_id: str, outfit_id: str) -> list[tuple[int, int, int]]:
    """Five-colour outfit palette anchored on (char_id, outfit_id)."""
    return [_det_color("outfit", char_id, outfit_id, i) for i in range(5)]


def stable_location_palette(location_id: str, mood: str) -> tuple[
    tuple[int, int, int], tuple[int, int, int]
]:
    """Two-colour gradient for the background of a location/mood."""
    return _det_color("loc_top", location_id, mood), _det_color(
        "loc_bot", location_id, mood
    )


@dataclass
class ShotRenderRequest:
    out_path: Path
    seed: int
    duration_s: int
    fps: int
    width: int
    height: int
    location_id: str
    mood: str
    key_action: str
    style_sha: str
    characters: list[dict]  # [{char_id, outfit_id}]


_FONT_CACHE: dict[int, ImageFont.ImageFont] = {}


def _ensure_font(size: int) -> ImageFont.ImageFont:
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    candidates = [
        # bundled fonts on Windows
        "C:/Windows/Fonts/msyh.ttc",  # MS YaHei (CJK)
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
    ]
    for c in candidates:
        if Path(c).exists():
            try:
                f = ImageFont.truetype(c, size=size)
                _FONT_CACHE[size] = f
                return f
            except Exception:
                continue
    f = ImageFont.load_default()
    _FONT_CACHE[size] = f
    return f


def _gradient_bg(w: int, h: int, top: tuple[int, int, int], bot: tuple[int, int, int]) -> Image.Image:
    """Fast vertical gradient via single bytearray fill."""
    raw = bytearray(w * h * 3)
    inv_h = 1.0 / max(1, h - 1)
    for y in range(h):
        t = y * inv_h
        r = int(top[0] * (1 - t) + bot[0] * t)
        g = int(top[1] * (1 - t) + bot[1] * t)
        b = int(top[2] * (1 - t) + bot[2] * t)
        row = bytes((r, g, b)) * w
        off = y * w * 3
        raw[off : off + w * 3] = row
    return Image.frombytes("RGB", (w, h), bytes(raw))


def _draw_character(
    draw: ImageDraw.ImageDraw,
    img: Image.Image,
    *,
    cx: int,
    cy: int,
    radius: int,
    face: tuple[int, int, int],
    outfit_palette: list[tuple[int, int, int]],
    char_id: str,
    seed: int,
) -> None:
    # Outfit body (rounded rectangle below the face)
    body_top = cy + int(radius * 0.7)
    body_bot = cy + radius * 4
    body_left = cx - radius * 2
    body_right = cx + radius * 2
    # Stripes of outfit colours -> robust against compression/downscale
    n = len(outfit_palette)
    for i, col in enumerate(outfit_palette):
        y0 = body_top + int((body_bot - body_top) * i / n)
        y1 = body_top + int((body_bot - body_top) * (i + 1) / n)
        draw.rectangle((body_left, y0, body_right, y1), fill=col)
    # Face circle
    draw.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        fill=face,
        outline=(20, 20, 20),
        width=3,
    )
    # Hair cap (top half of face, slightly darker face palette)
    hair = tuple(max(0, c - 60) for c in face)
    draw.pieslice(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        start=180,
        end=360,
        fill=hair,
    )
    # Char tag (tiny so QA OCR doesn't see it as on-screen text watermark)
    f = _ensure_font(14)
    draw.text((cx - radius, cy + radius * 4 + 4), char_id, fill=(240, 240, 240), font=f)


def render_frame(
    *,
    width: int,
    height: int,
    location_id: str,
    mood: str,
    key_action: str,
    style_sha: str,
    characters: list[dict],
    frame_seed: int,
    char_offset_y_jitter: int,
) -> Image.Image:
    top, bot = stable_location_palette(location_id, mood)
    img = _gradient_bg(width, height, top, bot)
    draw = ImageDraw.Draw(img)

    n = max(1, len(characters))
    radius = int(height * 0.07)
    base_y = height // 2 + char_offset_y_jitter
    spacing = width // (n + 1)
    for i, ch in enumerate(characters):
        char_id = ch["char_id"]
        outfit_id = ch.get("outfit_id", f"{char_id}_default")
        face = stable_face_palette(char_id)[0]
        outfit_palette = stable_outfit_palette(char_id, outfit_id)
        cx = spacing * (i + 1)
        _draw_character(
            draw,
            img,
            cx=cx,
            cy=base_y,
            radius=radius,
            face=face,
            outfit_palette=outfit_palette,
            char_id=char_id,
            seed=frame_seed,
        )

    # Caption (key action) — bottom safe area
    f_caption = _ensure_font(int(height * 0.045))
    txt = (key_action or "")[:36]
    draw.rectangle(
        (0, int(height * 0.85), width, int(height * 0.95)),
        fill=(0, 0, 0),
    )
    draw.text(
        (int(width * 0.05), int(height * 0.86)),
        txt,
        fill=(255, 255, 255),
        font=f_caption,
    )
    # Tiny style watermark (top-right)
    f_wm = _ensure_font(12)
    draw.text((width - 200, 8), f"STYLE:{style_sha[:8]}", fill=(240, 240, 240), font=f_wm)
    return img


def encode_mp4(frames_dir: Path, fps: int, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-framerate",
        str(fps),
        "-i",
        str(frames_dir / "frame_%05d.png"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def render_shot(req: ShotRenderRequest, frames_root: Path) -> Path:
    frames_dir = frames_root / req.out_path.stem
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    total_frames = req.duration_s * req.fps
    for i in range(total_frames):
        # Tiny per-frame jitter to avoid "frozen frame" artefact in QA, but
        # keep deterministic (seed -> jitter table).
        jitter = ((req.seed + i) % 17) - 8
        img = render_frame(
            width=req.width,
            height=req.height,
            location_id=req.location_id,
            mood=req.mood,
            key_action=req.key_action,
            style_sha=req.style_sha,
            characters=req.characters,
            frame_seed=req.seed + i,
            char_offset_y_jitter=jitter,
        )
        img.save(frames_dir / f"frame_{i:05d}.png")
    encode_mp4(frames_dir, req.fps, req.out_path)
    return req.out_path
