"""Stage 4: 单集视频合成 — ``pippit_shortplay_cvtob_video_compose_{fast,pro}720p``.

把 Stage 3 产出的分镜视频按时间线、字幕、BGM 自动合成为单集成片，输出
``final_video_url`` + ``final_video_cover_url``。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import httpx

from manhuaju.adapters.manhuaju_agent._base import ManhuajuAgentBase, ManhuajuAgentError
from manhuaju.adapters.manhuaju_agent.schemas import VideoCompositionResult


class VideoComposerAdapter(ManhuajuAgentBase):
    name = "ManhuajuAgent.VideoComposer"

    REQ_KEY_FAST = "pippit_shortplay_cvtob_video_compose_fast720p"
    REQ_KEY_PRO = "pippit_shortplay_cvtob_video_compose_pro720p"

    def compose(
        self,
        *,
        assets_id: str,
        thread_id: str,
        episode_id: str,
        budget_tier: str = "M",
        req_key: str | None = None,
    ) -> VideoCompositionResult:
        key = req_key or (self.REQ_KEY_PRO if budget_tier.upper() == "H" else self.REQ_KEY_FAST)
        body: dict[str, Any] = {
            "assets_id": assets_id,
            "thread_id": thread_id,
            "episode_id": str(episode_id),
        }
        return self.submit_and_poll(
            business="video_compose",
            req_key=key,
            submit_body=body,
            result_parser=lambda d: VideoCompositionResult.model_validate(d),
            operation_tag="manhuaju.compose",
            max_poll_s=float(self._cfg.get("max_poll_compose_s", 1800)),
        )

    def download(self, url: str, dest: Path, *, timeout_s: float = 300) -> Path:
        """同步下载远端 ``final_video_url`` 到本地。"""
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.stat().st_size > 0:
            return dest
        try:
            with httpx.stream("GET", url, timeout=timeout_s, follow_redirects=True) as resp:
                resp.raise_for_status()
                with dest.open("wb") as fp:
                    for chunk in resp.iter_bytes(chunk_size=1 << 20):
                        if chunk:
                            fp.write(chunk)
        except httpx.HTTPError as e:  # noqa: PERF203
            raise ManhuajuAgentError(
                code=-1, message=f"final video download failed: {e}", payload={"url": url}
            ) from e
        return dest

    @staticmethod
    def cache_filename(prefix: str, url: str, suffix: str = ".mp4") -> str:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}_{digest}{suffix}"
