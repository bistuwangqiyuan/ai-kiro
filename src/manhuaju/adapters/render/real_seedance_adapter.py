"""Real Volcengine Ark Seedance video adapter (M3 secondary).

Submits video-generation tasks to the Volcengine Ark `content_generation/tasks`
endpoint. If the Ark API key is missing or returns 401, gracefully degrades to
the configured mock fallback so a pilot run never blocks on Seedance.

Surface mirrors `MockXiaoyunqueAdapter` for AdapterFactory drop-in.
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

_API_BASE = "https://ark.cn-beijing.volces.com/api/v3"
_TASKS_ENDPOINT = f"{_API_BASE}/contents/generations/tasks"


@dataclass
class _Task:
    task_id: str
    remote_id: str | None
    status: str
    out_path: Path
    payload: dict[str, Any]
    fallback_used: bool = False


class RealSeedanceAdapter:
    name = "RealSeedanceAdapter"
    provider = "volcengine_seedance"

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
        self.artefacts_root = artefacts_root or Path("./live_renders_seedance")
        self.frames_root = frames_root or self.artefacts_root / "_frames"
        self.artefacts_root.mkdir(parents=True, exist_ok=True)
        self.mock_fallback = mock_fallback
        self._tasks: dict[str, _Task] = {}
        self._idem: dict[str, str] = {}
        self._poll_interval = float(self._cfg.get("poll_interval_s", 6))
        self._max_poll_s = float(self._cfg.get("max_poll_s", 600))
        self._model = self._cfg.get("seedance_model", "doubao-seedance-1-0-pro-250528")
        self._lock = threading.Lock()

    def inject_5xx_once(self, shot_id: str) -> None:  # noqa: ARG002 — parity stub
        return None

    def submit(self, **kwargs: Any) -> str:
        idem_key = kwargs["idem_key"]
        with self._lock:
            if idem_key in self._idem:
                return self._idem[idem_key]

        if not self._settings.volcengine_ark_key:
            return self._submit_via_mock(**kwargs)

        prompt = compose_fluent_video_prompt(
            prompt=str(kwargs.get("prompt", "")),
            characters=list(kwargs.get("characters") or []),
            location_id=str(kwargs.get("location_id", "")),
            mood=str(kwargs.get("mood", "")),
            key_action=str(kwargs.get("key_action", "")),
            max_len=1500,
        )
        # Ark Seedance reads generation params as trailing --flags in the text.
        prompt = f"{prompt} {self._ark_param_suffix(kwargs)}".strip()
        body = {
            "model": self._model,
            "content": [{"type": "text", "text": prompt}],
        }
        headers = {
            "Authorization": f"Bearer {self._settings.volcengine_ark_key}",
            "Content-Type": "application/json",
        }
        t0 = now_s()
        try:
            with httpx.Client(timeout=30) as client:
                r = client.post(_TASKS_ENDPOINT, headers=headers, json=body)
            duration = now_s() - t0
        except (httpx.HTTPError, OSError) as e:
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider="volcengine_seedance",
                    operation="video.submit",
                    model=self._model,
                    duration_s=now_s() - t0,
                    success=False,
                    error_class=type(e).__name__,
                )
            )
            return self._submit_via_mock(**kwargs)

        if r.status_code != 200:
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider="volcengine_seedance",
                    operation="video.submit",
                    model=self._model,
                    duration_s=duration,
                    success=False,
                    error_class=f"HTTP {r.status_code}",
                    extra={"body": r.text[:200]},
                )
            )
            return self._submit_via_mock(**kwargs)

        data = r.json()
        remote_id = data.get("id") or (data.get("data") or {}).get("id")
        self._cost.record(
            CostEntry(
                timestamp_s=time.time(),
                provider="volcengine_seedance",
                operation="video.submit",
                model=self._model,
                duration_s=duration,
                success=bool(remote_id),
                extra={"remote_task_id": remote_id, "shot_id": kwargs["shot_id"]},
            )
        )
        if not remote_id:
            return self._submit_via_mock(**kwargs)

        task_id = str(uuid.uuid4())
        out_path = self.artefacts_root / f"{kwargs['shot_id']}.mp4"
        with self._lock:
            self._tasks[task_id] = _Task(
                task_id=task_id,
                remote_id=remote_id,
                status="pending",
                out_path=out_path,
                payload={
                    "shot_id": kwargs["shot_id"],
                    "scene_id": kwargs["scene_id"],
                    "duration_s": kwargs["duration_s"],
                    "fps": kwargs["fps"],
                    "resolution": kwargs["resolution"],
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
        headers = {"Authorization": f"Bearer {self._settings.volcengine_ark_key}"}
        while time.time() < deadline:
            try:
                with httpx.Client(timeout=30) as client:
                    r = client.get(f"{_TASKS_ENDPOINT}/{t.remote_id}", headers=headers)
            except (httpx.HTTPError, OSError):
                time.sleep(self._poll_interval)
                continue
            if r.status_code != 200:
                time.sleep(self._poll_interval)
                continue
            data = r.json()
            status = (data.get("status") or "").lower()
            if status in ("succeeded", "completed"):
                video_url = ((data.get("content") or {}).get("video_url")) or data.get("video_url")
                if video_url and self._download(video_url, t.out_path):
                    rmb = self._cost.estimate_video(
                        "volcengine", float(t.payload["duration_s"])
                    )
                    self._cost.record(
                        CostEntry(
                            timestamp_s=time.time(),
                            provider="volcengine_seedance",
                            operation="video.complete",
                            model=self._model,
                            duration_s=0.0,
                            rmb=rmb,
                            success=True,
                        )
                    )
                    t.status = "succeeded"
                    return self._snapshot(t)
                t.status = "failed"
                return self._snapshot(t)
            if status == "failed":
                t.status = "failed"
                return self._snapshot(t)
            time.sleep(self._poll_interval)

        t.status = "failed"
        if self.mock_fallback is not None:
            t.fallback_used = True
            return self.mock_fallback.poll(task_id)
        return self._snapshot(t)

    @staticmethod
    def _ark_param_suffix(kwargs: dict[str, Any]) -> str:
        """Build Ark Seedance --flags for resolution/duration/ratio.

        Seedance accepts only 480p/720p/1080p and 3-12s. We clamp the per-shot
        seconds and map the project resolution to the closest supported tier.
        """
        res = str(kwargs.get("resolution", "720p")).lower()
        res_tier = "1080p" if "1080" in res else ("480p" if "480" in res else "720p")
        try:
            dur = int(round(float(kwargs.get("duration_s", 5))))
        except (TypeError, ValueError):
            dur = 5
        dur = max(3, min(dur, 12))
        ratio = str(kwargs.get("aspect_ratio") or kwargs.get("ratio") or "16:9")
        return f"--resolution {res_tier} --duration {dur} --ratio {ratio}"

    _MIN_REAL_VIDEO_BYTES = 200_000

    def _download(self, url: str, dest: Path) -> bool:
        last_size = -1
        for _ in range(3):
            try:
                with httpx.Client(
                    timeout=300,
                    follow_redirects=True,
                    headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"},
                ) as client:
                    r = client.get(url)
                if r.status_code != 200:
                    continue
                content = r.content
                last_size = len(content)
                ctype = r.headers.get("content-type", "")
                if "text" in ctype or "json" in ctype:
                    continue
                if last_size < self._MIN_REAL_VIDEO_BYTES:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
                return dest.stat().st_size >= self._MIN_REAL_VIDEO_BYTES
            except (httpx.HTTPError, OSError):
                continue
        return False

    def _submit_via_mock(self, **kwargs: Any) -> str:
        if self.mock_fallback is None:
            raise RuntimeError("Volcengine unavailable and no mock_fallback configured")
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
                    "model_version": f"volcengine:{self._model}",
                    "credits_spent": 0,
                    "width": w,
                    "height": h,
                }
                if t.status == "succeeded"
                else None
            ),
        }
