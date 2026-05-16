"""Mock Seedance 2.0 adapter (REQ-EXT-002 / design §8 fallback path)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from manhuaju.adapters.render.ffmpeg_render import (
    RESOLUTION_TABLE,
    ShotRenderRequest,
    render_shot,
)


class MockSeedanceAdapter:
    name = "MockSeedanceAdapter"
    provider = "seedance"

    def __init__(self, *, artefacts_root: Path, frames_root: Path) -> None:
        self.artefacts_root = artefacts_root
        self.frames_root = frames_root

    def synthesise(
        self,
        *,
        shot_id: str,
        prompt: str,
        seed: int,
        duration_s: int,
        fps: int,
        resolution: str,
        characters: list[dict],
        location_id: str,
        mood: str,
        key_action: str,
        style_sha: str,
        model_tier: str = "pro",
    ) -> dict[str, Any]:
        out = self.artefacts_root / f"{shot_id}.mp4"
        w, h = RESOLUTION_TABLE.get(resolution, (1280, 720))
        render_shot(
            ShotRenderRequest(
                out_path=out,
                seed=seed + 1,  # mark fallback path with +1 so phash differs slightly
                duration_s=duration_s,
                fps=fps,
                width=w,
                height=h,
                location_id=location_id,
                mood=mood,
                key_action=key_action,
                style_sha=style_sha,
                characters=characters,
            ),
            frames_root=self.frames_root,
        )
        return {
            "shot_id": shot_id,
            "status": "succeeded",
            "output_uri": str(out),
            "metadata": {
                "duration_s": float(duration_s),
                "fps": int(fps),
                "resolution": resolution,
                "model_version": "mock-seedance-2.0",
                "credits_spent": 0,
                "width": w,
                "height": h,
            },
            "degraded": True,
        }
