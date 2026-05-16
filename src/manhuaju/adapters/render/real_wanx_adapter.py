"""Real DashScope WanX 2.1 video adapter (M3 primary).

Implements the same surface as `MockXiaoyunqueAdapter` so it is a drop-in
replacement via `AdapterFactory`:

- `submit(...)` posts an async task to DashScope and returns a task_id.
- `poll(task_id)` polls task status; once succeeded, downloads the MP4 to
  `artefacts_root` and returns the standard snapshot shape.
- `inject_5xx_once(shot_id)` is a no-op (real chaos comes from the network);
  retained for API parity with the mock adapter so chaos tests still attach.

Model: wanx2.1-t2v-turbo (5s, 720p) — ~¥0.5 per video at the time of writing.
Budget caps are enforced at the pipeline level via `CostTracker`.

If `mock_fallback` is provided, network errors and 4xx degrade gracefully so
that hybrid mode never blocks an episode on DashScope outage.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from manhuaju.adapters.render.video_prompt import compose_fluent_video_prompt
from manhuaju.core.cost_tracker import CostEntry, CostTracker, now_s
from manhuaju.core.provider_settings import ProviderSettings

_API_BASE = "https://dashscope.aliyuncs.com/api/v1"
_VIDEO_ENDPOINT = f"{_API_BASE}/services/aigc/video-generation/video-synthesis"
_TASK_ENDPOINT = f"{_API_BASE}/tasks"


@dataclass
class _Task:
    task_id: str
    remote_id: str | None
    status: str
    out_path: Path
    payload: dict[str, Any]
    fallback_used: bool = False


class RealWanXAdapter:
    name = "RealWanXAdapter"
    provider = "dashscope_wanx"

    def __init__(
        self,
        *,
        settings: ProviderSettings,
        cost: CostTracker,
        config: dict[str, Any] | None = None,
        artefacts_root: Path | None = None,
        frames_root: Path | None = None,
        mock_fallback: Any | None = None,
    ) -> None:
        self._settings = settings
        self._cost = cost
        self._cfg = config or {}
        self.artefacts_root = artefacts_root or Path("./live_renders")
        self.frames_root = frames_root or self.artefacts_root / "_frames"
        self.artefacts_root.mkdir(parents=True, exist_ok=True)
        self.mock_fallback = mock_fallback
        self._tasks: dict[str, _Task] = {}
        self._idem: dict[str, str] = {}
        self._poll_interval = float(self._cfg.get("poll_interval_s", 6))
        self._max_poll_s = float(self._cfg.get("max_poll_s", 600))
        self._model = self._cfg.get("wanx_model", "wanx2.1-t2v-turbo")
        self._lock = threading.Lock()

    # -- API parity with mock adapter -------------------------------------
    def inject_5xx_once(self, shot_id: str) -> None:  # noqa: ARG002 — parity stub
        return None

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
        model_tier: str = "pro",  # noqa: ARG002
    ) -> str:
        with self._lock:
            if idem_key in self._idem:
                return self._idem[idem_key]

        # Delegate to mock fallback if no DashScope key configured.
        if not self._settings.dashscope_key:
            return self._submit_via_mock(
                idem_key=idem_key,
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
            )

        task_id = str(uuid.uuid4())
        out_path = self.artefacts_root / f"{shot_id}.mp4"

        full_prompt = self._compose_prompt(
            prompt=prompt,
            characters=characters,
            location_id=location_id,
            mood=mood,
            key_action=key_action,
        )
        size = _resolution_to_size(resolution)

        body = {
            "model": self._model,
            "input": {"prompt": full_prompt[:1500]},
            "parameters": {
                "size": size,
                "duration": min(max(int(duration_s), 3), 5),
                "prompt_extend": True,
                "seed": int(seed) & 0x7FFFFFFF,
            },
        }
        if self._cfg.get("debug_dump_root"):
            try:
                ddroot = Path(self._cfg["debug_dump_root"])
                ddroot.mkdir(parents=True, exist_ok=True)
                (ddroot / f"submit_{shot_id}.json").write_text(
                    __import__("json").dumps(
                        {
                            "shot_id": shot_id,
                            "raw_prompt": prompt,
                            "raw_characters": characters,
                            "location_id": location_id,
                            "mood": mood,
                            "key_action": key_action,
                            "composed": full_prompt,
                            "body": body,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            except OSError:
                pass
        headers = {
            "Authorization": f"Bearer {self._settings.dashscope_key}",
            "X-DashScope-Async": "enable",
            "Content-Type": "application/json",
        }
        t0 = now_s()
        try:
            with httpx.Client(timeout=30) as client:
                r = client.post(_VIDEO_ENDPOINT, headers=headers, json=body)
            duration = now_s() - t0
        except (httpx.HTTPError, OSError) as e:
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider="dashscope_wanx",
                    operation="video.submit",
                    model=self._model,
                    duration_s=now_s() - t0,
                    success=False,
                    error_class=type(e).__name__,
                )
            )
            return self._submit_via_mock(
                idem_key=idem_key,
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
            )

        if r.status_code != 200:
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider="dashscope_wanx",
                    operation="video.submit",
                    model=self._model,
                    duration_s=duration,
                    success=False,
                    error_class=f"HTTP {r.status_code}",
                    extra={"body": r.text[:200]},
                )
            )
            return self._submit_via_mock(
                idem_key=idem_key,
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
            )

        data = r.json()
        remote_id = (data.get("output") or {}).get("task_id")
        self._cost.record(
            CostEntry(
                timestamp_s=time.time(),
                provider="dashscope_wanx",
                operation="video.submit",
                model=self._model,
                duration_s=duration,
                success=bool(remote_id),
                extra={"remote_task_id": remote_id, "shot_id": shot_id},
            )
        )

        if not remote_id:
            return self._submit_via_mock(
                idem_key=idem_key,
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
            )

        with self._lock:
            self._tasks[task_id] = _Task(
                task_id=task_id,
                remote_id=remote_id,
                status="pending",
                out_path=out_path,
                payload={
                    "shot_id": shot_id,
                    "scene_id": scene_id,
                    "duration_s": duration_s,
                    "fps": fps,
                    "resolution": resolution,
                },
            )
            self._idem[idem_key] = task_id
        return task_id

    def poll(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            t = self._tasks.get(task_id)
        if t is None and self.mock_fallback is not None:
            return self.mock_fallback.poll(task_id)
        if t is None:
            return {"task_id": task_id, "status": "failed", "output_uri": None, "metadata": None}

        if t.fallback_used and self.mock_fallback is not None:
            return self.mock_fallback.poll(task_id)

        if t.status in ("succeeded", "failed"):
            return self._snapshot(t)

        deadline = time.time() + self._max_poll_s
        headers = {"Authorization": f"Bearer {self._settings.dashscope_key}"}
        while time.time() < deadline:
            t0 = now_s()
            try:
                with httpx.Client(timeout=30) as client:
                    r = client.get(f"{_TASK_ENDPOINT}/{t.remote_id}", headers=headers)
                duration = now_s() - t0
            except (httpx.HTTPError, OSError) as e:
                self._cost.record(
                    CostEntry(
                        timestamp_s=time.time(),
                        provider="dashscope_wanx",
                        operation="video.poll",
                        model=self._model,
                        duration_s=now_s() - t0,
                        success=False,
                        error_class=type(e).__name__,
                    )
                )
                time.sleep(self._poll_interval)
                continue

            if r.status_code != 200:
                self._cost.record(
                    CostEntry(
                        timestamp_s=time.time(),
                        provider="dashscope_wanx",
                        operation="video.poll",
                        model=self._model,
                        duration_s=duration,
                        success=False,
                        error_class=f"HTTP {r.status_code}",
                    )
                )
                time.sleep(self._poll_interval)
                continue

            data = r.json()
            output = data.get("output") or {}
            status = output.get("task_status", "PENDING")
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider="dashscope_wanx",
                    operation="video.poll",
                    model=self._model,
                    duration_s=duration,
                    success=True,
                    extra={"status": status},
                )
            )
            if status == "SUCCEEDED":
                video_url = output.get("video_url")
                if video_url and self._download(video_url, t.out_path):
                    rmb = self._cost.estimate_video(
                        "dashscope", float(t.payload["duration_s"])
                    )
                    self._cost.record(
                        CostEntry(
                            timestamp_s=time.time(),
                            provider="dashscope_wanx",
                            operation="video.complete",
                            model=self._model,
                            duration_s=0.0,
                            rmb=rmb,
                            success=True,
                            extra={"shot_id": t.payload["shot_id"]},
                        )
                    )
                    t.status = "succeeded"
                    return self._snapshot(t)
                t.status = "failed"
                return self._snapshot(t)
            if status == "FAILED":
                if self._cfg.get("debug_dump_root"):
                    try:
                        ddroot = Path(self._cfg["debug_dump_root"])
                        ddroot.mkdir(parents=True, exist_ok=True)
                        (ddroot / f"poll_failed_{t.payload['shot_id']}.json").write_text(
                            __import__("json").dumps(
                                {"shot_id": t.payload["shot_id"], "response": data},
                                ensure_ascii=False,
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                    except OSError:
                        pass
                t.status = "failed"
                return self._snapshot(t)
            time.sleep(self._poll_interval)

        t.status = "failed"
        if self.mock_fallback is not None:
            t.fallback_used = True
            return self.mock_fallback.poll(task_id)
        return self._snapshot(t)

    # -- helpers ----------------------------------------------------------

    def _compose_prompt(
        self,
        *,
        prompt: str,
        characters: list[dict],
        location_id: str,
        mood: str,
        key_action: str,
    ) -> str:
        return compose_fluent_video_prompt(
            prompt=prompt,
            characters=characters,
            location_id=location_id,
            mood=mood,
            key_action=key_action,
            max_len=1200,
        )

    def _download(self, url: str, dest: Path) -> bool:
        try:
            with httpx.Client(timeout=120) as client:
                r = client.get(url)
            if r.status_code != 200:
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            return dest.stat().st_size > 0
        except (httpx.HTTPError, OSError):
            return False

    def _submit_via_mock(self, **kwargs: Any) -> str:
        if self.mock_fallback is None:
            raise RuntimeError("DashScope unavailable and no mock_fallback configured")
        task_id = self.mock_fallback.submit(**kwargs)
        with self._lock:
            self._tasks[task_id] = _Task(
                task_id=task_id,
                remote_id=None,
                status="pending",
                out_path=self.artefacts_root / f"{kwargs['shot_id']}.mp4",
                payload={
                    "shot_id": kwargs["shot_id"],
                    "scene_id": kwargs["scene_id"],
                    "duration_s": kwargs["duration_s"],
                    "fps": kwargs["fps"],
                    "resolution": kwargs["resolution"],
                },
                fallback_used=True,
            )
            self._idem[kwargs["idem_key"]] = task_id
        return task_id

    def _snapshot(self, t: _Task) -> dict[str, Any]:
        from manhuaju.adapters.render.ffmpeg_render import RESOLUTION_TABLE

        w, h = RESOLUTION_TABLE.get(t.payload["resolution"], (1280, 720))
        return {
            "task_id": t.task_id,
            "status": t.status,
            "shot_id": t.payload["shot_id"],
            "output_uri": (str(t.out_path) if t.status == "succeeded" else None),
            "metadata": (
                {
                    "duration_s": float(t.payload["duration_s"]),
                    "fps": int(t.payload["fps"]),
                    "resolution": t.payload["resolution"],
                    "model_version": f"dashscope:{self._model}",
                    "credits_spent": 0,
                    "width": w,
                    "height": h,
                }
                if t.status == "succeeded"
                else None
            ),
        }


def _resolution_to_size(resolution: str) -> str:
    """WanX 2.1 t2v-turbo only allows fixed sizes; 1920×1080 is *not* supported."""
    table = {
        "720p": "1280*720",
        # Requested as broadcast tier — map to the maximum allowed 16:9 preset.
        "1080p": "1280*720",
        "1280x720": "1280*720",
        "1920x1080": "1280*720",
    }
    return table.get(resolution, "1280*720")
