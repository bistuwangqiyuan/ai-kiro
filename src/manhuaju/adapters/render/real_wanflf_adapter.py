"""fal.ai Wan 2.7 FLF (First-Last-Frame) 适配器 — Shell 4 脸漂移单镜重生 ★.

接口形态同 ``MockXiaoyunqueAdapter`` (``submit/poll``)，但仅用于单镜「锁脸重生」：
- 输入：失败镜头的 first_frame 与 last_frame（已抽帧上传 TOS）。
- 输出：新的镜头 mp4，FLF 让两端帧严格匹配参考图，中间运动 AI 平滑过渡。

参考：https://fal.ai/models/fal-ai/wan-2.7/flf
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from manhuaju.core.cost_tracker import CostEntry, CostTracker, now_s
from manhuaju.core.provider_settings import ProviderSettings

QUEUE_BASE = "https://queue.fal.run/fal-ai/wan-2.7/flf"


@dataclass
class _FLFTask:
    task_id: str
    remote_id: str | None
    status: str
    out_path: Path
    payload: dict[str, Any]


class RealWanFLFAdapter:
    """fal.ai Wan 2.7 first-last-frame face-locked regeneration."""

    name = "RealWanFLFAdapter"
    provider = "fal_wan27_flf"

    def __init__(
        self,
        *,
        settings: ProviderSettings,
        cost: CostTracker,
        config: dict[str, Any] | None = None,
        artefacts_root: Path | None = None,
        mock_fallback: Any | None = None,
    ) -> None:
        self._settings = settings
        self._cost = cost
        self._cfg = config or {}
        self.artefacts_root = artefacts_root or Path("./live_renders/flf")
        self.artefacts_root.mkdir(parents=True, exist_ok=True)
        self.mock_fallback = mock_fallback
        self._tasks: dict[str, _FLFTask] = {}
        self._idem: dict[str, str] = {}
        self._lock = threading.Lock()
        self._poll_interval = float(self._cfg.get("poll_interval_s", 5))
        self._max_poll_s = float(self._cfg.get("max_poll_s", 600))

    @property
    def available(self) -> bool:
        return bool(self._settings.fal_key)

    def regenerate(
        self,
        *,
        idem_key: str,
        shot_id: str,
        first_frame_url: str,
        last_frame_url: str,
        prompt: str,
        duration_s: int = 5,
        resolution: str = "720p",
        seed: int = 0,
    ) -> dict[str, Any]:
        """One-shot synchronous regenerate (submit → poll → snapshot)."""
        task_id = self.submit(
            idem_key=idem_key,
            shot_id=shot_id,
            first_frame_url=first_frame_url,
            last_frame_url=last_frame_url,
            prompt=prompt,
            duration_s=duration_s,
            resolution=resolution,
            seed=seed,
        )
        return self.poll(task_id)

    def submit(
        self,
        *,
        idem_key: str,
        shot_id: str,
        first_frame_url: str,
        last_frame_url: str,
        prompt: str,
        duration_s: int = 5,
        resolution: str = "720p",  # noqa: ARG002
        seed: int = 0,
    ) -> str:
        with self._lock:
            if idem_key in self._idem:
                return self._idem[idem_key]
        if not self.available:
            return self._submit_via_mock(
                idem_key=idem_key, shot_id=shot_id, prompt=prompt,
                duration_s=duration_s, seed=seed,
            )

        body = {
            "prompt": prompt[:600],
            "first_image_url": first_frame_url,
            "last_image_url": last_frame_url,
            "num_frames": min(max(int(duration_s) * 24, 60), 240),
            "seed": int(seed) & 0x7FFFFFFF,
        }
        headers = {
            "Authorization": f"Key {self._settings.fal_key}",
            "Content-Type": "application/json",
        }
        t0 = now_s()
        try:
            with httpx.Client(timeout=30) as c:
                r = c.post(QUEUE_BASE, headers=headers, json=body)
            dur = now_s() - t0
        except (httpx.HTTPError, OSError) as e:
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider=self.provider,
                    operation="flf.submit",
                    model="wan-2.7-flf",
                    duration_s=now_s() - t0,
                    success=False,
                    error_class=type(e).__name__,
                )
            )
            return self._submit_via_mock(
                idem_key=idem_key, shot_id=shot_id, prompt=prompt,
                duration_s=duration_s, seed=seed,
            )

        if r.status_code != 200:
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider=self.provider,
                    operation="flf.submit",
                    model="wan-2.7-flf",
                    duration_s=dur,
                    success=False,
                    error_class=f"HTTP {r.status_code}",
                    extra={"body": r.text[:200]},
                )
            )
            return self._submit_via_mock(
                idem_key=idem_key, shot_id=shot_id, prompt=prompt,
                duration_s=duration_s, seed=seed,
            )

        try:
            data = r.json()
            remote_id = data.get("request_id")
        except Exception:  # noqa: BLE001
            remote_id = None

        self._cost.record(
            CostEntry(
                timestamp_s=time.time(),
                provider=self.provider,
                operation="flf.submit",
                model="wan-2.7-flf",
                duration_s=dur,
                success=bool(remote_id),
                extra={"remote_id": remote_id, "shot_id": shot_id},
            )
        )

        if not remote_id:
            return self._submit_via_mock(
                idem_key=idem_key, shot_id=shot_id, prompt=prompt,
                duration_s=duration_s, seed=seed,
            )

        tid = str(uuid.uuid4())
        with self._lock:
            self._tasks[tid] = _FLFTask(
                task_id=tid,
                remote_id=remote_id,
                status="pending",
                out_path=self.artefacts_root / f"{shot_id}_flf.mp4",
                payload={"shot_id": shot_id, "duration_s": duration_s},
            )
            self._idem[idem_key] = tid
        return tid

    def poll(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            t = self._tasks.get(task_id)
        if t is None and self.mock_fallback is not None:
            return self.mock_fallback.poll(task_id)
        if t is None:
            return {"task_id": task_id, "status": "failed", "output_uri": None, "metadata": None}

        deadline = time.time() + self._max_poll_s
        headers = {"Authorization": f"Key {self._settings.fal_key}"}
        status_url = f"{QUEUE_BASE}/requests/{t.remote_id}/status"
        result_url = f"{QUEUE_BASE}/requests/{t.remote_id}"

        while time.time() < deadline:
            try:
                with httpx.Client(timeout=30) as c:
                    r = c.get(status_url, headers=headers)
                if r.status_code == 200:
                    status = (r.json() or {}).get("status", "").lower()
                    if status in ("completed", "success", "done"):
                        # fetch result
                        with httpx.Client(timeout=30) as c:
                            rr = c.get(result_url, headers=headers)
                        if rr.status_code != 200:
                            time.sleep(self._poll_interval)
                            continue
                        body = rr.json() or {}
                        video_url = (body.get("video") or {}).get("url") or body.get("video_url")
                        if video_url and self._download(video_url, t.out_path):
                            rmb = self._cost.estimate_video("fal", float(t.payload["duration_s"]))
                            self._cost.record(
                                CostEntry(
                                    timestamp_s=time.time(),
                                    provider=self.provider,
                                    operation="flf.complete",
                                    model="wan-2.7-flf",
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
                    if status in ("failed", "error"):
                        t.status = "failed"
                        return self._snapshot(t)
            except (httpx.HTTPError, OSError):
                pass
            time.sleep(self._poll_interval)

        t.status = "failed"
        return self._snapshot(t)

    def _download(self, url: str, dest: Path) -> bool:
        try:
            with httpx.Client(timeout=120) as c:
                r = c.get(url)
            if r.status_code != 200:
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(r.content)
            return dest.stat().st_size > 0
        except (httpx.HTTPError, OSError):
            return False

    def _submit_via_mock(
        self,
        *,
        idem_key: str,
        shot_id: str,
        prompt: str,  # noqa: ARG002
        duration_s: int,
        seed: int,  # noqa: ARG002
    ) -> str:
        if self.mock_fallback is None:
            raise RuntimeError("fal.ai unavailable and no mock_fallback configured")
        task_id = self.mock_fallback.submit(
            idem_key=idem_key,
            shot_id=shot_id,
            scene_id=shot_id,
            prompt=prompt,
            prompt_sha=idem_key,
            seed=seed,
            duration_s=duration_s,
            fps=24,
            resolution="720p",
            characters=[],
            location_id="repair",
            mood="neutral",
            key_action="flf_repair",
            style_sha=idem_key[:8],
        )
        with self._lock:
            self._tasks[task_id] = _FLFTask(
                task_id=task_id,
                remote_id=None,
                status="pending",
                out_path=self.artefacts_root / f"{shot_id}_flf.mp4",
                payload={"shot_id": shot_id, "duration_s": duration_s},
            )
            self._idem[idem_key] = task_id
        return task_id

    def _snapshot(self, t: _FLFTask) -> dict[str, Any]:
        return {
            "task_id": t.task_id,
            "status": t.status,
            "shot_id": t.payload["shot_id"],
            "output_uri": str(t.out_path) if t.status == "succeeded" else None,
            "metadata": (
                {
                    "duration_s": float(t.payload["duration_s"]),
                    "fps": 24,
                    "resolution": "720p",
                    "model_version": "fal-ai/wan-2.7/flf",
                    "credits_spent": 0,
                    "width": 1280,
                    "height": 720,
                }
                if t.status == "succeeded"
                else None
            ),
        }
