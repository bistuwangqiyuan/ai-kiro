"""Mock Xiaoyunque Agent 2.0 adapter (REQ-EXT-001 / design §8).

Implements:
- submit() with idempotency key
- poll(task_id) returning status; in M2 we render synchronously when poll is
  first called (or directly inside submit) and persist artefact.
- webhook simulation (not used in M2 happy path because tests poll).
- chaos hook: a counter that fails once with HTTP-style 500 on a chosen task,
  then succeeds on retry (REQ-EXT-002 / REQ-PILOT-009).
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from manhuaju.adapters.render.ffmpeg_render import (
    RESOLUTION_TABLE,
    ShotRenderRequest,
    render_shot,
)
from manhuaju.adapters.render.mock_seedance_adapter import MockSeedanceAdapter


class XiaoyunqueAPIError(Exception):
    """Mocked 5xx-style error to drive chaos test."""

    def __init__(self, status: int, msg: str) -> None:
        super().__init__(msg)
        self.status = status


@dataclass
class _Task:
    task_id: str
    status: str
    out_path: Path | None
    payload: dict[str, Any]
    retries: int = 0


class MockXiaoyunqueAdapter:
    name = "MockXiaoyunqueAdapter"
    provider = "xiaoyunque"

    def __init__(
        self,
        *,
        artefacts_root: Path,
        frames_root: Path,
        seedance_fallback: MockSeedanceAdapter | None = None,
    ) -> None:
        self.artefacts_root = artefacts_root
        self.frames_root = frames_root
        self.seedance_fallback = seedance_fallback
        self._tasks: dict[str, _Task] = {}
        self._idem: dict[str, str] = {}  # idem_key -> task_id
        self._chaos_targets: set[str] = set()
        self._chaos_lock = threading.Lock()

    # -- chaos hook -------------------------------------------------------
    def inject_5xx_once(self, shot_id: str) -> None:
        with self._chaos_lock:
            self._chaos_targets.add(shot_id)

    # -- API surface ------------------------------------------------------
    def submit(
        self,
        *,
        idem_key: str,
        shot_id: str,
        scene_id: str,
        prompt: str,
        prompt_sha: str,
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
    ) -> str:
        if idem_key in self._idem:
            return self._idem[idem_key]
        with self._chaos_lock:
            if shot_id in self._chaos_targets:
                self._chaos_targets.discard(shot_id)
                raise XiaoyunqueAPIError(500, f"chaos: simulated 5xx for {shot_id}")
        task_id = str(uuid.uuid4())
        out_path = self.artefacts_root / f"{shot_id}.mp4"
        self._tasks[task_id] = _Task(
            task_id=task_id,
            status="pending",
            out_path=out_path,
            payload=dict(
                shot_id=shot_id,
                scene_id=scene_id,
                prompt=prompt,
                prompt_sha=prompt_sha,
                seed=seed,
                duration_s=duration_s,
                fps=fps,
                resolution=resolution,
                characters=characters,
                location_id=location_id,
                mood=mood,
                key_action=key_action,
                style_sha=style_sha,
                model_tier=model_tier,
            ),
        )
        self._idem[idem_key] = task_id
        return task_id

    def poll(self, task_id: str) -> dict[str, Any]:
        t = self._tasks[task_id]
        if t.status in ("succeeded", "failed"):
            return self._snapshot(t)
        # render now (synchronous mock)
        try:
            w, h = RESOLUTION_TABLE.get(t.payload["resolution"], (1280, 720))
            out = render_shot(
                ShotRenderRequest(
                    out_path=t.out_path,  # type: ignore[arg-type]
                    seed=t.payload["seed"],
                    duration_s=t.payload["duration_s"],
                    fps=t.payload["fps"],
                    width=w,
                    height=h,
                    location_id=t.payload["location_id"],
                    mood=t.payload["mood"],
                    key_action=t.payload["key_action"],
                    style_sha=t.payload["style_sha"],
                    characters=t.payload["characters"],
                ),
                frames_root=self.frames_root,
            )
            t.status = "succeeded"
            t.out_path = out
        except Exception as e:
            t.status = "failed"
            t.payload["error"] = str(e)
        return self._snapshot(t)

    def _snapshot(self, t: _Task) -> dict[str, Any]:
        return {
            "task_id": t.task_id,
            "status": t.status,
            "shot_id": t.payload["shot_id"],
            "output_uri": (str(t.out_path) if t.out_path else None) if t.status == "succeeded" else None,
            "metadata": (
                {
                    "duration_s": float(t.payload["duration_s"]),
                    "fps": int(t.payload["fps"]),
                    "resolution": t.payload["resolution"],
                    "model_version": "mock-xiaoyunque-2.0",
                    "credits_spent": 0,
                    "width": RESOLUTION_TABLE.get(t.payload["resolution"], (1280, 720))[0],
                    "height": RESOLUTION_TABLE.get(t.payload["resolution"], (1280, 720))[1],
                }
                if t.status == "succeeded"
                else None
            ),
        }
