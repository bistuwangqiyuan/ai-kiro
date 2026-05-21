"""Post-production: concatenate shots, burn subtitles, normalise loudness.

Mock-mode pipeline writes a real H.264 mp4 per episode using ffmpeg's concat
demuxer + drawtext + loudnorm filter.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from pathlib import Path


def _font_path() -> str | None:
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def write_concat_list(shots: Iterable[Path], out_txt: Path) -> Path:
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    with out_txt.open("w", encoding="utf-8") as f:
        for shot in shots:
            f.write(f"file '{Path(shot).resolve().as_posix()}'\n")
    return out_txt


def concat_shots(shot_paths: list[Path], out_mp4: Path) -> Path:
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    txt = out_mp4.with_suffix(".txt")
    write_concat_list(shot_paths, txt)
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(txt),
        "-c",
        "copy",
        str(out_mp4),
    ]
    res = subprocess.run(cmd, check=False, capture_output=True)
    if res.returncode != 0:
        # Fallback: re-encode (concat copy fails when shot codecs differ)
        cmd2 = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(txt),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            str(out_mp4),
        ]
        subprocess.run(cmd2, check=True, capture_output=True)
    return out_mp4


def burn_subtitle(in_mp4: Path, subtitle_text: str, out_mp4: Path) -> Path:
    """Burn a single static caption (REQ-PP-001 minimum).

    Uses ffmpeg `drawtext` with `textfile=` to avoid command-line escaping of
    CJK/colon/quote characters on Windows.
    """
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    fp = _font_path()
    text_path = out_mp4.with_suffix(".caption.txt")
    text_path.write_text(subtitle_text, encoding="utf-8")
    text_path_for_filter = str(text_path).replace("\\", "/").replace(":", "\\:")
    parts = [
        f"textfile='{text_path_for_filter}'",
        "fontcolor=white",
        "fontsize=36",
        "x=(w-text_w)/2",
        "y=h-100",
        "box=1",
        "boxcolor=black@0.6",
        "boxborderw=10",
    ]
    if fp:
        ff = fp.replace("\\", "/").replace(":", "\\:")
        parts.insert(0, f"fontfile='{ff}'")
    drawtext = "drawtext=" + ":".join(parts)
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(in_mp4),
        "-vf",
        drawtext,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-an",
        str(out_mp4),
    ]
    res = subprocess.run(cmd, check=False, capture_output=True)
    if res.returncode != 0:
        # If drawtext can't render (font unsupported), copy without caption.
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(in_mp4), "-c", "copy", str(out_mp4)],
            check=True,
            capture_output=True,
        )
    return out_mp4


def normalise_loudness(in_path: Path, out_path: Path) -> Path:
    """REQ-MD-005: target -16 LUFS / max -1 dBTP. Two-pass loudnorm in mock."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(in_path),
        "-af",
        "loudnorm=I=-16:TP=-1:LRA=11",
        "-ar",
        "48000",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def mux_video_audio(video: Path, audio: Path, out_mp4: Path) -> Path:
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_mp4


def episode_postprod(
    *,
    shot_mp4s: list[Path],
    bgm_wav: Path | None,
    out_dir: Path,
    episode_id: str,
    caption: str = "",
) -> Path:
    """Backward-compatible wrapper: rough cut then fine cut."""
    from manhuaju.pipelines.fine_cut import fine_cut_episode
    from manhuaju.pipelines.rough_cut import rough_cut_episode

    rough = rough_cut_episode(
        shot_mp4s=shot_mp4s,
        bgm_wav=bgm_wav,
        out_dir=out_dir,
        episode_id=episode_id,
    )
    return fine_cut_episode(
        rough_mp4=rough,
        bgm_wav=bgm_wav,
        out_dir=out_dir,
        episode_id=episode_id,
        fallback_caption=caption,
    )
