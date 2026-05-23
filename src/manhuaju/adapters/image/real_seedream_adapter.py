"""火山 Seedream 5.0 / 即梦 4.6 图像适配器 — Shell 2 角色与场景资产产线 ★.

接口契约：
- ``generate(prompt, ...) -> list[GeneratedImage]`` 返回多张图（已下载到本地 + 可选 TOS 上传）。
- ``generate_group(prompt, num_images=14, ...) -> list[GeneratedImage]`` 一组角色四视图 + 表情。
- ``generate_with_reference(prompt, reference_images, num_images, ...) -> list[GeneratedImage]``
  Jimeng 4.6 走「参考图引导」生成姿态/服装变体。

graceful fallback：未配 Visual SDK 或 SDK 失败 → 走 ``mock_fallback``（默认 Pillow 占位）。
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from manhuaju.core.cost_tracker import CostEntry, CostTracker, now_s
from manhuaju.core.provider_settings import ProviderSettings


@dataclass
class GeneratedImage:
    local_path: Path
    public_url: str | None        # TOS / CDN URL（None 表示仅本地）
    width: int
    height: int
    seed: int
    prompt: str
    model: str
    provider: str
    bytes: int


class _VolcengineImageBase:
    """Common base for Seedream + Jimeng (Volcengine Visual SDK)."""

    def __init__(
        self,
        *,
        settings: ProviderSettings,
        cost: CostTracker,
        config: dict[str, Any] | None = None,
        artefacts_root: Path | None = None,
        tos_storage: Any | None = None,
        mock_fallback: Any | None = None,
    ) -> None:
        self._settings = settings
        self._cost = cost
        self._cfg = config or {}
        self.artefacts_root = artefacts_root or Path("./live_assets/images")
        self.artefacts_root.mkdir(parents=True, exist_ok=True)
        self.tos = tos_storage
        self.mock_fallback = mock_fallback
        self._svc: Any | None = None
        self._lock = threading.Lock()
        self._init_sdk()

    def _init_sdk(self) -> None:
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

    @property
    def available(self) -> bool:
        return self._svc is not None and self._settings.has_xiaoyunque

    # ----- helpers -----
    def _submit_async(self, params: dict[str, Any]) -> str | None:
        try:
            resp = self._svc.cv_sync2async_submit_task(params)
        except Exception:  # noqa: BLE001
            return None
        if isinstance(resp, dict):
            data = resp.get("data") or resp.get("Data") or {}
            if isinstance(data, dict):
                return str(data.get("task_id") or data.get("TaskID") or "") or None
        return None

    def _poll_async(self, req_key: str, task_id: str, *, timeout_s: float = 180) -> dict[str, Any]:
        poll = float(self._cfg.get("poll_interval_s", 3))
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                resp = self._svc.cv_sync2async_get_result(
                    {"req_key": req_key, "task_id": task_id}
                )
            except Exception:  # noqa: BLE001
                time.sleep(poll)
                continue
            status = self._status(resp)
            if status in ("done", "success", "succeeded"):
                return resp if isinstance(resp, dict) else {}
            if status in ("failed", "error"):
                return resp if isinstance(resp, dict) else {}
            time.sleep(poll)
        return {}

    @staticmethod
    def _status(resp: Any) -> str:
        if isinstance(resp, dict):
            data = resp.get("data") or resp.get("Data") or {}
            if isinstance(data, dict):
                return str(data.get("status") or data.get("Status") or "").lower()
        return ""

    @staticmethod
    def _extract_images(resp: Any) -> list[bytes | str]:
        """Returns either list of bytes (base64) or list of URL strings."""
        if not isinstance(resp, dict):
            return []
        data = resp.get("data") or resp.get("Data") or {}
        if not isinstance(data, dict):
            return []
        # base64 inline images
        b64s = data.get("binary_data_base64") or data.get("binary_data_base_64") or []
        if isinstance(b64s, list) and b64s:
            return [_decode_b64(x) for x in b64s if isinstance(x, str)]
        # URL list
        urls = data.get("image_urls") or data.get("ImageUrls") or data.get("output_urls") or []
        if isinstance(urls, list) and urls:
            return [str(u) for u in urls if isinstance(u, str)]
        return []

    def _save_and_publish(
        self,
        items: list[bytes | str],
        *,
        prefix: str,
        prompt: str,
        seed: int,
        model: str,
        width: int,
        height: int,
        upload_to_tos: bool,
    ) -> list[GeneratedImage]:
        results: list[GeneratedImage] = []
        for i, item in enumerate(items):
            if isinstance(item, (bytes, bytearray)):
                data = bytes(item)
            elif isinstance(item, str):
                data = self._download(item)
                if data is None:
                    continue
            else:
                continue
            fname = f"{prefix}_{i:02d}_{uuid.uuid4().hex[:6]}.png"
            local = self.artefacts_root / fname
            local.write_bytes(data)
            public_url: str | None = None
            if upload_to_tos and self.tos is not None:
                try:
                    res = self.tos.upload_file(local, key=f"images/{prefix}/{fname}")
                    public_url = res.presigned_url
                except Exception:  # noqa: BLE001
                    public_url = None
            results.append(
                GeneratedImage(
                    local_path=local,
                    public_url=public_url,
                    width=width,
                    height=height,
                    seed=seed,
                    prompt=prompt,
                    model=model,
                    provider="volcengine_visual",
                    bytes=len(data),
                )
            )
        return results

    @staticmethod
    def _download(url: str) -> bytes | None:
        try:
            with httpx.Client(timeout=60) as c:
                r = c.get(url)
            return r.content if r.status_code == 200 else None
        except (httpx.HTTPError, OSError):
            return None


def _decode_b64(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    try:
        return base64.b64decode(s + pad)
    except (base64.binascii.Error, ValueError):
        return b""


class RealSeedreamAdapter(_VolcengineImageBase):
    """Seedream 5.0 — 主角参考图大组 (8 张多角度 + 表情)."""

    name = "RealSeedreamAdapter"
    provider = "volcengine_seedream"

    def generate(
        self,
        *,
        prompt: str,
        num_images: int = 4,
        aspect_ratio: str = "3:4",
        seed: int = 0,
        upload_to_tos: bool = True,
        prefix: str = "seedream",
    ) -> list[GeneratedImage]:
        if not self.available:
            return self._fallback(prompt=prompt, num_images=num_images, prefix=prefix)

        req_key = self._cfg.get("seedream_req_key") or self._settings.seedream_req_key
        # Seedream T2I 是 sync 类型；用 cv_process 兼容
        w, h = _aspect_to_wh(aspect_ratio)
        params = {
            "req_key": req_key,
            "prompt": prompt[:2000],
            "width": w,
            "height": h,
            "seed": int(seed) & 0x7FFFFFFF,
            "num_images": int(num_images),
            "return_url": False,            # 返回 base64 更可靠
            "deep_thinking": True,          # tech.md 关键开关
        }
        t0 = now_s()
        try:
            resp = self._svc.cv_process(params)
            success = True
        except Exception as e:  # noqa: BLE001
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider=self.provider,
                    operation="image.generate",
                    model=req_key,
                    duration_s=now_s() - t0,
                    success=False,
                    error_class=type(e).__name__,
                )
            )
            return self._fallback(prompt=prompt, num_images=num_images, prefix=prefix)

        dur = now_s() - t0
        items = self._extract_images(resp)
        if not items:
            # try async fallback
            task = self._submit_async(params)
            if task:
                resp = self._poll_async(req_key, task, timeout_s=180)
                items = self._extract_images(resp)

        if not items:
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider=self.provider,
                    operation="image.generate",
                    model=req_key,
                    duration_s=dur,
                    success=False,
                    error_class="empty_response",
                )
            )
            return self._fallback(prompt=prompt, num_images=num_images, prefix=prefix)

        rmb = self._cost.estimate_image("volcengine_seedream", len(items))
        self._cost.record(
            CostEntry(
                timestamp_s=time.time(),
                provider=self.provider,
                operation="image.generate",
                model=req_key,
                duration_s=dur,
                rmb=rmb,
                success=success,
                extra={"n_images": len(items), "prompt_head": prompt[:80]},
            )
        )
        return self._save_and_publish(
            items,
            prefix=prefix,
            prompt=prompt,
            seed=seed,
            model=req_key,
            width=w,
            height=h,
            upload_to_tos=upload_to_tos,
        )

    def generate_group(
        self,
        *,
        prompt: str,
        num_images: int = 8,
        aspect_ratio: str = "3:4",
        seed: int = 0,
        upload_to_tos: bool = True,
        prefix: str = "char_group",
    ) -> list[GeneratedImage]:
        """tech.md 外壳 2：一次出 8 张多角度（正/45/侧/背 + 4 表情）。"""
        prompt_aug = (
            prompt
            + "\n生成角色设定图组：正面 / 45度 / 侧面 / 背面全身 + 4 个表情特写（喜怒哀羞），"
            "保持同一角色相同的脸部特征、发型、服饰。"
        )
        return self.generate(
            prompt=prompt_aug,
            num_images=num_images,
            aspect_ratio=aspect_ratio,
            seed=seed,
            upload_to_tos=upload_to_tos,
            prefix=prefix,
        )

    def _fallback(self, *, prompt: str, num_images: int, prefix: str) -> list[GeneratedImage]:
        if self.mock_fallback is None:
            return []
        with contextlib.suppress(Exception):
            return list(
                self.mock_fallback.generate(
                    prompt=prompt, num_images=num_images, prefix=prefix
                )
            )
        return []


class RealJimengAdapter(_VolcengineImageBase):
    """即梦 4.6 — 姿态/服装变体 + 参考图引导."""

    name = "RealJimengAdapter"
    provider = "volcengine_jimeng"

    def generate_with_reference(
        self,
        *,
        prompt: str,
        reference_images: list[str | Path],
        num_images: int = 6,
        aspect_ratio: str = "3:4",
        seed: int = 0,
        upload_to_tos: bool = True,
        prefix: str = "jimeng_variant",
    ) -> list[GeneratedImage]:
        if not self.available:
            return self._fallback(prompt=prompt, num_images=num_images, prefix=prefix)

        req_key = self._cfg.get("jimeng_req_key") or self._settings.jimeng_req_key
        w, h = _aspect_to_wh(aspect_ratio)

        # 上传参考图到 TOS 拿 URL（小云雀/即梦都需要 URL 输入）
        ref_urls = self._upload_refs(reference_images)
        params = {
            "req_key": req_key,
            "prompt": prompt[:2000],
            "width": w,
            "height": h,
            "seed": int(seed) & 0x7FFFFFFF,
            "num_images": int(num_images),
            "image_urls": ref_urls[:4],
            "return_url": False,
        }
        t0 = now_s()
        try:
            resp = self._svc.cv_process(params)
        except Exception as e:  # noqa: BLE001
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider=self.provider,
                    operation="image.with_ref",
                    model=req_key,
                    duration_s=now_s() - t0,
                    success=False,
                    error_class=type(e).__name__,
                )
            )
            return self._fallback(prompt=prompt, num_images=num_images, prefix=prefix)

        dur = now_s() - t0
        items = self._extract_images(resp)
        if not items:
            task = self._submit_async(params)
            if task:
                resp = self._poll_async(req_key, task, timeout_s=180)
                items = self._extract_images(resp)

        if not items:
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider=self.provider,
                    operation="image.with_ref",
                    model=req_key,
                    duration_s=dur,
                    success=False,
                    error_class="empty_response",
                )
            )
            return self._fallback(prompt=prompt, num_images=num_images, prefix=prefix)

        rmb = self._cost.estimate_image("volcengine_jimeng", len(items))
        self._cost.record(
            CostEntry(
                timestamp_s=time.time(),
                provider=self.provider,
                operation="image.with_ref",
                model=req_key,
                duration_s=dur,
                rmb=rmb,
                success=True,
                extra={"n_images": len(items), "n_refs": len(ref_urls)},
            )
        )
        return self._save_and_publish(
            items,
            prefix=prefix,
            prompt=prompt,
            seed=seed,
            model=req_key,
            width=w,
            height=h,
            upload_to_tos=upload_to_tos,
        )

    # 简单生成（无参考）
    def generate(self, **kwargs: Any) -> list[GeneratedImage]:
        kwargs.setdefault("reference_images", [])
        return self.generate_with_reference(**kwargs)

    def _upload_refs(self, refs: list[str | Path]) -> list[str]:
        out: list[str] = []
        for r in refs:
            s = str(r)
            if s.startswith("http://") or s.startswith("https://"):
                out.append(s)
                continue
            if self.tos is not None:
                try:
                    res = self.tos.upload_file(r)
                    out.append(res.presigned_url)
                    continue
                except Exception:  # noqa: BLE001
                    pass
            out.append(s)
        return out

    def _fallback(self, *, prompt: str, num_images: int, prefix: str) -> list[GeneratedImage]:
        if self.mock_fallback is None:
            return []
        with contextlib.suppress(Exception):
            return list(
                self.mock_fallback.generate(
                    prompt=prompt, num_images=num_images, prefix=prefix
                )
            )
        return []


def _aspect_to_wh(ar: str) -> tuple[int, int]:
    """Seedream/Jimeng 通常支持几个固定档；这里映射为常用值。"""
    table = {
        "9:16": (768, 1344),
        "3:4": (864, 1152),
        "1:1": (1024, 1024),
        "4:3": (1152, 864),
        "16:9": (1344, 768),
    }
    return table.get(ar, (1024, 1024))
