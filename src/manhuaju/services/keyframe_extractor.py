"""Keyframe extraction (REQ-TM-002).

Two strategies:

* ``extract_from_comic_pages`` — accepts a list of comic page paths +
  optional panel coordinates → returns one keyframe per panel.
* ``extract_from_video`` — accepts a video path + an FPS → returns
  scene-cut keyframes via a deterministic mock detector. The real path
  uses ``opencv-python``'s ``cv2.VideoCapture`` + perceptual hash diff.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

#: REQ-TM-002 anchor: target ≥ 1 keyframe per second of source video.
DEFAULT_KEYFRAMES_PER_SECOND = 1.0
#: REQ-TM-002: scene-cut threshold. Higher → fewer keyframes.
DEFAULT_SCENE_CUT_THRESHOLD = 0.35


@dataclass(frozen=True)
class Keyframe:
    keyframe_id: str
    source_path: str
    source_kind: str  # "comic" | "video"
    timestamp_s: float
    panel_index: int | None
    image_path: str
    sha: str


def _sha(*parts: object) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def extract_from_comic_pages(
    page_paths: list[Path | str],
    panels_per_page: int = 1,
) -> list[Keyframe]:
    """REQ-TM-002: comic page → keyframes (one per panel)."""

    out: list[Keyframe] = []
    for page_idx, p in enumerate(page_paths, start=1):
        for panel in range(panels_per_page):
            kid = f"comic-p{page_idx}-panel{panel}"
            out.append(
                Keyframe(
                    keyframe_id=kid,
                    source_path=str(p),
                    source_kind="comic",
                    timestamp_s=0.0,
                    panel_index=panel,
                    image_path=str(p),
                    sha=_sha(p, page_idx, panel),
                )
            )
    return out


def extract_from_video(
    video_path: Path | str,
    duration_s: float,
    fps: float = DEFAULT_KEYFRAMES_PER_SECOND,
    scene_cut_threshold: float = DEFAULT_SCENE_CUT_THRESHOLD,
) -> list[Keyframe]:
    """REQ-TM-002 (video branch): emit one keyframe every ``1/fps`` seconds.

    The detector is a deterministic mock that emits a keyframe at every
    integer multiple of the period, keeping the byte-identical output
    promised by the e2e pilot.
    """

    if duration_s <= 0:
        raise ValueError("duration_s must be > 0")
    if fps <= 0:
        raise ValueError("fps must be > 0")
    period = 1.0 / fps
    out: list[Keyframe] = []
    t = 0.0
    idx = 0
    while t < duration_s:
        kid = f"video-{idx:04d}"
        out.append(
            Keyframe(
                keyframe_id=kid,
                source_path=str(video_path),
                source_kind="video",
                timestamp_s=round(t, 4),
                panel_index=None,
                image_path=f"{video_path}#frame_{idx:04d}.png",
                sha=_sha(video_path, idx, t),
            )
        )
        idx += 1
        t += period
    # NOTE: scene_cut_threshold is consumed by the real adapter; the mock keeps
    # it in the signature for interface compatibility.
    _ = scene_cut_threshold
    return out
