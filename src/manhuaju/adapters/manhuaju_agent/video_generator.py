"""Stage 3: 分镜视频生成 — ``pippit_shortplay_cvtob_video_generate_{fast,pro}720p``.

按 ``budget_tier`` 选档：

- ``H`` (high quality) → ``pro720p`` (Seedance 2.0 720p)
- ``M`` / ``L`` (mass) → ``fast720p`` (Seedance 2.0 fast 720p)

返回 ``VideoGenerationResult``，含整集分镜数组、每分镜的 ``VideoURL`` /
``ShotStatusMap``。若有分镜失败，调用方可重试该 ``episode_id``（接口会原地复用
已成功的镜头，仅重生失败的）。
"""

from __future__ import annotations

from manhuaju.adapters.manhuaju_agent._base import ManhuajuAgentBase
from manhuaju.adapters.manhuaju_agent.schemas import VideoGenerationResult


class VideoGeneratorAdapter(ManhuajuAgentBase):
    name = "ManhuajuAgent.VideoGenerator"

    REQ_KEY_FAST = "pippit_shortplay_cvtob_video_generate_fast720p"
    REQ_KEY_PRO = "pippit_shortplay_cvtob_video_generate_pro720p"

    def generate(
        self,
        *,
        assets_id: str,
        thread_id: str,
        episode_id: str,
        run_id: str | None = None,
        budget_tier: str = "M",
        req_key: str | None = None,
    ) -> VideoGenerationResult:
        key = req_key or (self.REQ_KEY_PRO if budget_tier.upper() == "H" else self.REQ_KEY_FAST)
        body = {
            "assets_id": assets_id,
            "thread_id": thread_id,
            "run_id": run_id or self.gen_run_id(f"v{budget_tier.lower()}"),
            "episode_id": str(episode_id),
        }
        return self.submit_and_poll(
            business="video_generate",
            req_key=key,
            submit_body=body,
            result_parser=lambda d: VideoGenerationResult.model_validate(d),
            operation_tag="manhuaju.video",
            max_poll_s=float(self._cfg.get("max_poll_video_s", 3600)),
        )

    def generate_with_retry(
        self,
        *,
        assets_id: str,
        thread_id: str,
        episode_id: str,
        budget_tier: str = "M",
        max_retries: int = 2,
    ) -> VideoGenerationResult:
        """如果有分镜失败，自动重试 ``max_retries`` 次。

        接口语义：同 ``(assets_id, thread_id, episode_id)`` 再次提交时，已成功的
        镜头不会重复生成，只重生失败/缺失的镜头。
        """
        result = self.generate(
            assets_id=assets_id,
            thread_id=thread_id,
            episode_id=episode_id,
            budget_tier=budget_tier,
        )
        episode = result.episode(str(episode_id))
        if episode is None:
            return result

        for _attempt in range(max_retries):
            failed = episode.failed_shots
            if not failed or episode.all_shots_done:
                break
            result = self.generate(
                assets_id=assets_id,
                thread_id=thread_id,
                episode_id=episode_id,
                budget_tier=budget_tier,
            )
            episode = result.episode(str(episode_id))
            if episode is None:
                break
        return result
