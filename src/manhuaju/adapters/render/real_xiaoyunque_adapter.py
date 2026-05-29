"""Real Volcengine 小云雀 Agent 2.0「有参考」适配器 — v4 ★ 核心渲染肌肉.

实现 tech.md 第四节给出的调用骨架，符合 [小云雀-智能生视频 Agent 2.0 有参考-接口文档](https://www.volcengine.com/docs/85621/2359610)。

接口契约（与 `MockXiaoyunqueAdapter` / `RealWanXAdapter` 完全一致）:
- ``submit(...) -> task_id``
- ``poll(task_id) -> {task_id, status, shot_id, output_uri, metadata}``
- ``inject_5xx_once(shot_id)`` — chaos hook（停留为 no-op，真链路不做注入）

新增能力（v4 关键）:
- ``submit_episode(...)`` —— 单次 submit 整集（75s），返回 ``shot_videos`` 数组用于单镜重生。
- ``character_references`` / ``scene_references`` / ``style_reference`` 字段透传 TOS 预签名 URL。
- ``model_tier``: ``"pro"`` → ``skylark_video_agent_v2_with_ref``;
  ``"fast"`` → ``skylark_duanju_manhuaju_seedance_2_fast_720p``。

跨集一致性「防线 3」：默认 ``weight=0.85``，可在 `live.video.reference_weight` 调整。

Graceful fallback：网络异常 / req_key 拒绝 / 配额耗尽 → ``mock_fallback`` 兜底。
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from manhuaju.adapters.render.video_prompt import compose_fluent_video_prompt
from manhuaju.core.cost_tracker import CostEntry, CostTracker, now_s
from manhuaju.core.provider_settings import ProviderSettings


def _is_jimeng_req_key(req_key: str) -> bool:
    """True for 即梦 (Jimeng) general video models, which use a minimal schema."""
    return str(req_key or "").lower().startswith("jimeng")


def _jimeng_video_params(
    *,
    req_key: str,
    prompt: str,
    aspect_ratio: str,
    duration_s: int,
    fps: int,
    seed: int,
) -> dict[str, Any]:
    """Build the param set Jimeng video models accept.

    Jimeng v3.0 t2v/i2v take ``frames`` (not ``duration``); commonly the API
    supports 121 frames (~5s) or 241 frames (~10s) @ 24fps. We snap to the
    nearest supported step and never send skylark-only reference fields.
    """
    eff_fps = fps if fps in (24,) else 24
    raw_frames = max(1, int(round(float(duration_s) * eff_fps)))
    # Snap to the two officially supported lengths (5s / 10s) to avoid 50200.
    frames = 121 if raw_frames <= 181 else 241
    return {
        "req_key": req_key,
        "prompt": prompt[:4000],
        "aspect_ratio": aspect_ratio,
        "frames": frames,
        "seed": int(seed) & 0x7FFFFFFF,
    }


@dataclass
class _XYQTask:
    task_id: str
    remote_id: str | None
    status: str
    out_path: Path
    payload: dict[str, Any]
    fallback_used: bool = False
    shot_videos: list[str] = field(default_factory=list)


class RealXiaoyunqueAdapter:
    """火山小云雀 Agent 2.0「有参考」适配器。"""

    name = "RealXiaoyunqueAdapter"
    provider = "volcengine_xiaoyunque"

    def __init__(
        self,
        *,
        settings: ProviderSettings,
        cost: CostTracker,
        config: dict[str, Any] | None = None,
        artefacts_root: Path | None = None,
        frames_root: Path | None = None,
        tos_storage: Any | None = None,
        mock_fallback: Any | None = None,
    ) -> None:
        self._settings = settings
        self._cost = cost
        self._cfg = config or {}
        self.artefacts_root = artefacts_root or Path("./live_renders")
        self.frames_root = frames_root or self.artefacts_root / "_frames"
        self.artefacts_root.mkdir(parents=True, exist_ok=True)
        self.frames_root.mkdir(parents=True, exist_ok=True)
        self.tos = tos_storage  # type: ignore[assignment]
        self.mock_fallback = mock_fallback
        self._tasks: dict[str, _XYQTask] = {}
        self._idem: dict[str, str] = {}
        self._lock = threading.Lock()
        self._poll_interval = float(self._cfg.get("poll_interval_s", 10))
        self._max_poll_s = float(self._cfg.get("max_poll_s", 2400))
        self._ref_weight = float(self._cfg.get("reference_weight", 0.85))
        self._svc: Any | None = None
        self._init_visual_sdk()

    # ----- SDK init -----
    def _init_visual_sdk(self) -> None:
        if not self._settings.has_xiaoyunque:
            return
        try:
            from volcengine.visual.VisualService import VisualService  # type: ignore[import-untyped]

            self._svc = VisualService()
            self._svc.set_ak(self._settings.volcengine_visual_ak)
            self._svc.set_sk(self._settings.volcengine_visual_sk)
            with contextlib.suppress(AttributeError):
                self._svc.set_region(self._settings.volcengine_visual_region)
        except ImportError:
            self._svc = None

    # ----- chaos parity -----
    def inject_5xx_once(self, shot_id: str) -> None:  # noqa: ARG002
        return None

    # ===================================================================
    # 主入口（与 Mock/WanX 同形：单 shot 提交）
    # ===================================================================
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
        reference_images: list[str] | None = None,
    ) -> str:
        with self._lock:
            if idem_key in self._idem:
                return self._idem[idem_key]

        if self._svc is None or not self._settings.has_xiaoyunque:
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

        req_key = self._pick_req_key(model_tier)
        full_prompt = self._compose_prompt(
            prompt=prompt,
            characters=characters,
            location_id=location_id,
            mood=mood,
            key_action=key_action,
        )

        if _is_jimeng_req_key(req_key):
            # 即梦 (Jimeng) 通用视频模型只认 {req_key, prompt, aspect_ratio,
            # seed, frames}；小云雀短剧专用的 character_references /
            # scene_references / duration 字段会被拒（50200）或忽略，因此走
            # 精简参数集，并把秒数换算成帧数 (frames = duration * fps)。
            params = _jimeng_video_params(
                req_key=req_key,
                prompt=full_prompt,
                aspect_ratio=self._resolution_to_aspect(resolution),
                duration_s=duration_s,
                fps=fps,
                seed=seed,
            )
        else:
            char_refs_payload = self._build_char_refs(characters, reference_images or [])
            scene_refs_payload = self._build_scene_refs(location_id, reference_images or [])
            style_ref_url = self._extract_style_ref(reference_images or [])

            params = {
                "req_key": req_key,
                "prompt": full_prompt[:4000],
                "aspect_ratio": self._resolution_to_aspect(resolution),
                "duration": min(max(int(duration_s), 3), 10),
                "seed": int(seed) & 0x7FFFFFFF,
            }
            if char_refs_payload:
                params["character_references"] = char_refs_payload
            if scene_refs_payload:
                params["scene_references"] = scene_refs_payload
            if style_ref_url:
                params["style_reference"] = style_ref_url

            params = {k: v for k, v in params.items() if v not in (None, [], "")}

        self._maybe_dump("submit", shot_id, {"params": params, "full_prompt": full_prompt})

        t0 = now_s()
        try:
            resp = self._svc.cv_sync2async_submit_task(params)
            duration = now_s() - t0
        except Exception as e:  # noqa: BLE001
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider=self.provider,
                    operation="video.submit",
                    model=req_key,
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

        remote_id = self._extract_remote_id(resp)
        self._cost.record(
            CostEntry(
                timestamp_s=time.time(),
                provider=self.provider,
                operation="video.submit",
                model=req_key,
                duration_s=duration,
                success=bool(remote_id),
                extra={"remote_task_id": remote_id, "shot_id": shot_id, "req_key": req_key},
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
            self._tasks[task_id] = _XYQTask(
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
                    "req_key": req_key,
                    "model_tier": model_tier,
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

        if self._svc is None:
            t.status = "failed"
            return self._snapshot(t)

        deadline = time.time() + self._max_poll_s
        while time.time() < deadline:
            t0 = now_s()
            try:
                resp = self._svc.cv_sync2async_get_result(
                    {"req_key": t.payload["req_key"], "task_id": t.remote_id}
                )
                dur = now_s() - t0
            except Exception as e:  # noqa: BLE001
                self._cost.record(
                    CostEntry(
                        timestamp_s=time.time(),
                        provider=self.provider,
                        operation="video.poll",
                        model=t.payload["req_key"],
                        duration_s=now_s() - t0,
                        success=False,
                        error_class=type(e).__name__,
                    )
                )
                time.sleep(self._poll_interval)
                continue

            status = self._extract_status(resp)
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider=self.provider,
                    operation="video.poll",
                    model=t.payload["req_key"],
                    duration_s=dur,
                    success=True,
                    extra={"status": status},
                )
            )

            if status in ("done", "success", "succeeded"):
                video_url = self._extract_video_url(resp)
                shot_videos = self._extract_shot_videos(resp)
                if video_url and self._download(video_url, t.out_path):
                    t.shot_videos = self._download_shot_videos(shot_videos, t.payload["shot_id"])
                    rmb = self._cost.estimate_video(
                        "volcengine_xiaoyunque", float(t.payload["duration_s"])
                    )
                    self._cost.record(
                        CostEntry(
                            timestamp_s=time.time(),
                            provider=self.provider,
                            operation="video.complete",
                            model=t.payload["req_key"],
                            duration_s=0.0,
                            rmb=rmb,
                            success=True,
                            extra={
                                "shot_id": t.payload["shot_id"],
                                "shot_videos_n": len(t.shot_videos),
                            },
                        )
                    )
                    t.status = "succeeded"
                    return self._snapshot(t)
                t.status = "failed"
                return self._snapshot(t)

            if status in ("failed", "error"):
                self._maybe_dump("poll_failed", t.payload["shot_id"], {"response": _safe(resp)})
                t.status = "failed"
                if self.mock_fallback is not None:
                    t.fallback_used = True
                    return self.mock_fallback.poll(task_id)
                return self._snapshot(t)

            time.sleep(self._poll_interval)

        t.status = "failed"
        if self.mock_fallback is not None:
            t.fallback_used = True
            return self.mock_fallback.poll(task_id)
        return self._snapshot(t)

    # ===================================================================
    # 整集模式（v4 推荐）—— 一次 submit 75s 全集
    # ===================================================================
    def submit_episode(
        self,
        *,
        episode_id: str,
        script_text: str,
        character_refs: dict[str, list[str]],
        scene_refs: dict[str, list[str]] | None = None,
        style_ref: str | None = None,
        aspect_ratio: str = "9:16",
        duration_s: int = 75,
        seed: int = 20260516,
        model_tier: str = "pro",
        idem_key: str | None = None,
    ) -> str:
        """tech.md 第四节调用骨架的整集版本。返回 internal task_id。"""
        idem = idem_key or f"ep:{episode_id}:{model_tier}:{seed}"
        with self._lock:
            if idem in self._idem:
                return self._idem[idem]

        if self._svc is None or not self._settings.has_xiaoyunque:
            # 整集模式无 mock 兜底（由上层 episode pipeline 决定降级到 per-shot）。
            raise RuntimeError("xiaoyunque visual SDK unavailable for submit_episode")

        req_key = self._pick_req_key(model_tier)
        char_refs_payload = [
            {
                "char_id": cid,
                "image_urls": self._presign(urls),
                "weight": self._ref_weight,
            }
            for cid, urls in character_refs.items()
            if urls
        ]
        scene_refs_payload = [
            {"loc_id": lid, "image_urls": self._presign(urls)}
            for lid, urls in (scene_refs or {}).items()
            if urls
        ]
        style_url = self._presign([style_ref])[0] if style_ref else None

        params: dict[str, Any] = {
            "req_key": req_key,
            "prompt": script_text[:8000],
            "aspect_ratio": aspect_ratio,
            "duration": int(duration_s),
            "seed": int(seed) & 0x7FFFFFFF,
        }
        if char_refs_payload:
            params["character_references"] = char_refs_payload
        if scene_refs_payload:
            params["scene_references"] = scene_refs_payload
        if style_url:
            params["style_reference"] = style_url

        params = {k: v for k, v in params.items() if v not in (None, [], "")}

        task_id = str(uuid.uuid4())
        out_path = self.artefacts_root / f"{episode_id}.mp4"

        self._maybe_dump("submit_episode", episode_id, {"params": params})
        t0 = now_s()
        try:
            resp = self._svc.cv_sync2async_submit_task(params)
        except Exception as e:  # noqa: BLE001
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider=self.provider,
                    operation="episode.submit",
                    model=req_key,
                    duration_s=now_s() - t0,
                    success=False,
                    error_class=type(e).__name__,
                )
            )
            raise

        remote_id = self._extract_remote_id(resp)
        self._cost.record(
            CostEntry(
                timestamp_s=time.time(),
                provider=self.provider,
                operation="episode.submit",
                model=req_key,
                duration_s=now_s() - t0,
                success=bool(remote_id),
                extra={"remote_task_id": remote_id, "episode_id": episode_id},
            )
        )

        with self._lock:
            self._tasks[task_id] = _XYQTask(
                task_id=task_id,
                remote_id=remote_id,
                status="pending",
                out_path=out_path,
                payload={
                    "shot_id": episode_id,        # 复用 shot_id 字段做整集主键
                    "scene_id": episode_id,
                    "duration_s": duration_s,
                    "fps": 24,
                    "resolution": "1080p",
                    "req_key": req_key,
                    "model_tier": model_tier,
                    "episode": True,
                },
            )
            self._idem[idem] = task_id
        return task_id

    # ===================================================================
    # helpers
    # ===================================================================
    def _pick_req_key(self, tier: str) -> str:
        if tier == "fast":
            return self._cfg.get("duanju_req_key") or self._settings.duanju_req_key
        return self._cfg.get("xiaoyunque_req_key") or self._settings.xiaoyunque_req_key

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
            max_len=3800,
        )

    def _presign(self, urls: list[str | None]) -> list[str]:
        """Turn local paths / file URIs into TOS presigned URLs."""
        out: list[str] = []
        for u in urls:
            if not u:
                continue
            if isinstance(u, str) and (u.startswith("http://") or u.startswith("https://")):
                out.append(u)
                continue
            if self.tos is not None:
                try:
                    result = self.tos.upload_file(u)
                    out.append(result.presigned_url)
                    continue
                except Exception:
                    pass
            out.append(str(u))
        return out

    def _build_char_refs(
        self, characters: list[dict], reference_images: list[str]
    ) -> list[dict[str, Any]]:
        """Group reference_images by character (heuristic on path)."""
        by_char: dict[str, list[str]] = defaultdict(list)
        for ch in characters:
            cid = ch.get("char_id")
            if not cid:
                continue
            for ri in reference_images:
                if cid in str(ri):
                    by_char[cid].append(ri)
        result: list[dict[str, Any]] = []
        for cid, urls in by_char.items():
            if urls:
                result.append(
                    {
                        "char_id": cid,
                        "image_urls": self._presign(urls),
                        "weight": self._ref_weight,
                    }
                )
        if not result and characters and reference_images:
            # 全部归到第一个角色
            result.append(
                {
                    "char_id": characters[0].get("char_id", "lead"),
                    "image_urls": self._presign(reference_images[:4]),
                    "weight": self._ref_weight,
                }
            )
        return result

    def _build_scene_refs(
        self, location_id: str, reference_images: list[str]
    ) -> list[dict[str, Any]]:
        scene_imgs = [r for r in reference_images if f"scene_{location_id}" in str(r) or "/scenes/" in str(r)]
        if not scene_imgs:
            return []
        return [{"loc_id": location_id, "image_urls": self._presign(scene_imgs[:3])}]

    def _extract_style_ref(self, reference_images: list[str]) -> str | None:
        style_imgs = [r for r in reference_images if "style_" in str(r) or "_style." in str(r)]
        if not style_imgs:
            return None
        return self._presign(style_imgs[:1])[0]

    @staticmethod
    def _resolution_to_aspect(resolution: str) -> str:
        table = {
            "720p": "16:9",
            "1080p": "16:9",
            "1080x1920": "9:16",
            "720x1280": "9:16",
            "1920x1080": "16:9",
            "1280x720": "16:9",
            "1080x1080": "1:1",
        }
        return table.get(resolution, "9:16")

    @staticmethod
    def _extract_remote_id(resp: Any) -> str | None:
        if isinstance(resp, dict):
            data = resp.get("data") or resp.get("Data") or {}
            if isinstance(data, dict):
                return str(data.get("task_id") or data.get("TaskID") or "") or None
            if isinstance(resp.get("task_id"), str):
                return resp["task_id"]
        return None

    @staticmethod
    def _extract_status(resp: Any) -> str:
        if isinstance(resp, dict):
            data = resp.get("data") or resp.get("Data") or {}
            if isinstance(data, dict):
                s = data.get("status") or data.get("Status") or ""
                return str(s).lower()
        return "unknown"

    @staticmethod
    def _extract_video_url(resp: Any) -> str | None:
        if not isinstance(resp, dict):
            return None
        data = resp.get("data") or resp.get("Data") or {}
        if not isinstance(data, dict):
            return None
        for key in ("video_url", "VideoURL", "video", "output_video_url"):
            v = data.get(key)
            if isinstance(v, str) and v:
                return v
        return None

    @staticmethod
    def _extract_shot_videos(resp: Any) -> list[str]:
        if not isinstance(resp, dict):
            return []
        data = resp.get("data") or resp.get("Data") or {}
        if not isinstance(data, dict):
            return []
        for key in ("shot_videos", "ShotVideos", "shots", "segments"):
            v = data.get(key)
            if isinstance(v, list):
                urls: list[str] = []
                for item in v:
                    if isinstance(item, str):
                        urls.append(item)
                    elif isinstance(item, dict):
                        for k in ("video_url", "url"):
                            if isinstance(item.get(k), str):
                                urls.append(item[k])
                                break
                return urls
        return []

    # Real Jimeng/小云雀 clips are multi-MB; anything tiny is an error page
    # (e.g. a CDN redirect/JSON/HTML body returned with HTTP 200). Treat such
    # downloads as failures so we don't pass a 16KB placeholder downstream.
    _MIN_REAL_VIDEO_BYTES = 200_000

    def _download(self, url: str, dest: Path) -> bool:
        last_size = -1
        for attempt in range(3):
            try:
                # follow_redirects is False by default in httpx — the aigc-cloud
                # CDN can 302 to the real asset, so we MUST opt in or we'd save
                # the redirect body. A browser-like UA avoids some 403/empty
                # responses on certain egress paths (e.g. FaaS).
                with httpx.Client(
                    timeout=300,
                    follow_redirects=True,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0 Safari/537.36"
                        ),
                        "Accept": "*/*",
                    },
                ) as client:
                    r = client.get(url)
                if r.status_code != 200:
                    continue
                content = r.content
                last_size = len(content)
                ctype = r.headers.get("content-type", "")
                # Reject obvious non-video error bodies.
                if "text" in ctype or "json" in ctype:
                    continue
                if last_size < self._MIN_REAL_VIDEO_BYTES:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
                return dest.stat().st_size >= self._MIN_REAL_VIDEO_BYTES
            except (httpx.HTTPError, OSError):
                continue
        self._maybe_dump(
            "download_failed",
            dest.stem,
            {"url": url, "last_size": last_size},
        )
        return False

    def _download_shot_videos(self, urls: list[str], base_id: str) -> list[str]:
        out: list[str] = []
        for i, url in enumerate(urls):
            dest = self.artefacts_root / f"{base_id}_sh{i:03d}.mp4"
            if self._download(url, dest):
                out.append(str(dest))
        return out

    def _maybe_dump(self, kind: str, key: str, payload: dict[str, Any]) -> None:
        root = self._cfg.get("debug_dump_root")
        if not root:
            return
        try:
            p = Path(root)
            p.mkdir(parents=True, exist_ok=True)
            (p / f"{kind}_{key}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _submit_via_mock(self, **kwargs: Any) -> str:
        if self.mock_fallback is None:
            raise RuntimeError("xiaoyunque unavailable and no mock_fallback configured")
        task_id = self.mock_fallback.submit(**kwargs)
        with self._lock:
            self._tasks[task_id] = _XYQTask(
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
                    "req_key": "mock",
                    "model_tier": "mock",
                },
                fallback_used=True,
            )
            self._idem[kwargs["idem_key"]] = task_id
        return task_id

    def _snapshot(self, t: _XYQTask) -> dict[str, Any]:
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
                    "model_version": f"volcengine:{t.payload.get('req_key', 'xiaoyunque-v2')}",
                    "model_tier": t.payload.get("model_tier"),
                    "credits_spent": 0,
                    "width": w,
                    "height": h,
                    "shot_videos": list(t.shot_videos),
                }
                if t.status == "succeeded"
                else None
            ),
        }


def _safe(obj: Any) -> Any:
    """Make API responses JSON-serializable for debug dumps."""
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)
