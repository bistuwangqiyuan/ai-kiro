"""端到端流水线 ``docx → final video.mp4``（火山「短剧漫剧 Agent」原生 4 步链）.

```mermaid
flowchart LR
  docx[docx 输入] --> sa[1. 剧本解析] --> md[2. 素材设计] --> vg[3. 视频生成] --> vc[4. 视频合成] --> mp4[final.mp4]
```

公开 API：

- :class:`ManhuajuAgentPipeline` — 持有 4 个适配器，提供 :meth:`run_project` /
  :meth:`run_episode` 两个入口。
- 入参为 docx 公网 URL（可用 :class:`manhuaju.adapters.storage.tos_storage.TOSStorage`
  上传后取预签名 URL）。
- 出参为 :class:`ProjectProduction`，包含每集的 ``final_video_local_path`` 和
  ``final_video_url``。

```python
from manhuaju.adapters.manhuaju_agent import (
    ManhuajuAgentBase, ScriptAnalyzerAdapter, MaterialDesignerAdapter,
    VideoGeneratorAdapter, VideoComposerAdapter,
)
from manhuaju.pipelines.manhuaju_agent_flow import ManhuajuAgentPipeline

p = ManhuajuAgentPipeline(...)
project = p.run_project(docx_url="https://...奶茶里的戒指.docx", budget_tier="M")
print(project.episodes[0].final_video_local_path)
```
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from manhuaju.adapters.manhuaju_agent.material_designer import MaterialDesignerAdapter
from manhuaju.adapters.manhuaju_agent.mock_manhuaju_agent_adapter import (
    MockManhuajuAgentAdapter,
)
from manhuaju.adapters.manhuaju_agent.schemas import (
    EpisodeProduction,
    ProjectProduction,
)
from manhuaju.adapters.manhuaju_agent.script_analyzer import ScriptAnalyzerAdapter
from manhuaju.adapters.manhuaju_agent.video_composer import VideoComposerAdapter
from manhuaju.adapters.manhuaju_agent.video_generator import VideoGeneratorAdapter

log = logging.getLogger(__name__)


@dataclass
class ManhuajuAgentPipeline:
    """4 步流水线编排器。

    Attributes:
        script_analyzer / material_designer / video_generator / video_composer:
            4 个适配器，类型可以是 real 或 mock。
        output_root: 成片保存根目录（每个项目一个子目录）。
        skip_compose: True 时跳过 stage 4（仅产分镜视频，不合成成片）。
    """

    script_analyzer: ScriptAnalyzerAdapter | MockManhuajuAgentAdapter
    material_designer: MaterialDesignerAdapter | MockManhuajuAgentAdapter
    video_generator: VideoGeneratorAdapter | MockManhuajuAgentAdapter
    video_composer: VideoComposerAdapter | MockManhuajuAgentAdapter
    output_root: Path
    skip_compose: bool = False

    @classmethod
    def mock(cls, output_root: Path | None = None) -> "ManhuajuAgentPipeline":
        """全 mock 流水线（无网络依赖）。"""
        mock = MockManhuajuAgentAdapter(artefacts_root=output_root)
        return cls(
            script_analyzer=mock,
            material_designer=mock,
            video_generator=mock,
            video_composer=mock,
            output_root=output_root or Path("./api_data/manhuaju_agent_mock"),
        )

    def run_episode(
        self,
        *,
        assets_id: str,
        thread_id: str,
        episode_id: str,
        budget_tier: str = "M",
        output_dir: Path | None = None,
    ) -> EpisodeProduction:
        """跑单集（stage 3 + stage 4）。

        要求事先已跑过 ``analyze`` 与 ``design`` 拿到 ``assets_id`` / ``thread_id``。
        """
        target_dir = output_dir or (self.output_root / f"ep_{episode_id}")
        target_dir.mkdir(parents=True, exist_ok=True)

        log.info("[stage 3] video.generate episode=%s tier=%s", episode_id, budget_tier)
        gen = self.video_generator.generate_with_retry(
            assets_id=assets_id,
            thread_id=thread_id,
            episode_id=episode_id,
            budget_tier=budget_tier,
        )
        storyboard = gen.episode(str(episode_id))

        production = EpisodeProduction(
            episode_id=str(episode_id),
            storyboard=storyboard,
            extra={"video_generate_charge": gen.charge_count},
        )

        if self.skip_compose:
            log.info("[stage 4] skipped (skip_compose=True)")
            return production

        log.info("[stage 4] video.compose episode=%s", episode_id)
        compose = self.video_composer.compose(
            assets_id=assets_id,
            thread_id=thread_id,
            episode_id=episode_id,
            budget_tier=budget_tier,
        )
        production.composition = compose

        if compose.final_video_url:
            cache_name = VideoComposerAdapter.cache_filename(
                f"ep{episode_id}", compose.final_video_url
            )
            local_path = target_dir / cache_name
            try:
                self.video_composer.download(compose.final_video_url, local_path)
                production.final_video_local_path = str(local_path)
            except Exception as e:  # noqa: BLE001
                log.warning("download failed for episode %s: %s", episode_id, e)
                production.extra["download_error"] = str(e)

        return production

    def run_project(
        self,
        *,
        file_url: str,
        budget_tier: str = "M",
        visual_style: str = "真人写实, 电影风格, 冷色调,都市女频",
        video_ratio: str = "16:9",
        max_episodes: int | None = None,
        project_id: str | None = None,
    ) -> ProjectProduction:
        """端到端跑完一部剧：4 步全跑通。

        Args:
            file_url: docx 公网 URL（建议先上传到 TOS 取预签名 URL）。
            budget_tier: ``H`` 高质量（pro 720p），``M``/``L`` 量产（fast 720p）。
            max_episodes: 仅跑前 N 集（用于试制 / 演示）。
            project_id: 工程标识；默认 ``thread_id`` 缩位。
        """
        t0 = time.time()
        log.info("[stage 1] script.analyze url=%s tier=%s", file_url, budget_tier)
        script = self.script_analyzer.analyze(
            file_url=file_url,
            visual_style=visual_style,
            video_ratio=video_ratio,
        )

        log.info(
            "[stage 2] material.design thread=%s assets=%s",
            script.thread_id,
            script.assets_id,
        )
        materials = self.material_designer.design(
            assets_id=script.assets_id,
            thread_id=script.thread_id,
        )

        proj_id = project_id or f"prj_{script.thread_id[-12:]}"
        out_dir = self.output_root / proj_id
        out_dir.mkdir(parents=True, exist_ok=True)

        episode_ids = script.episode_ids
        if max_episodes is not None and max_episodes > 0:
            episode_ids = episode_ids[:max_episodes]

        episodes: list[EpisodeProduction] = []
        for ep_id in episode_ids:
            episode = self.run_episode(
                assets_id=script.assets_id,
                thread_id=script.thread_id,
                episode_id=ep_id,
                budget_tier=budget_tier,
                output_dir=out_dir / f"ep_{ep_id}",
            )
            # 附上 episode 标题（来自 stage 1 的 EpisodeAssets）
            for ea in script.script_detail.episode_assets:
                if ea.episode_id == ep_id:
                    episode.episode_title = ea.episode_title or ea.episode_name
                    break
            episodes.append(episode)

        production = ProjectProduction(
            project_id=proj_id,
            thread_id=script.thread_id,
            assets_id=script.assets_id,
            script=script,
            materials=materials,
            episodes=episodes,
        )
        log.info(
            "pipeline done project=%s episodes=%s elapsed=%.1fs",
            proj_id,
            len(episodes),
            time.time() - t0,
        )
        return production


def build_pipeline_from_bundle(bundle: Any) -> ManhuajuAgentPipeline:
    """从 ``AdapterBundle`` 构造 pipeline（透传 settings/cost/config）。

    若 bundle 没有 ``manhuaju_agent_*`` 适配器（早期版本），降级到 mock。
    """
    if all(
        getattr(bundle, attr, None) is not None
        for attr in (
            "manhuaju_script_analyzer",
            "manhuaju_material_designer",
            "manhuaju_video_generator",
            "manhuaju_video_composer",
        )
    ):
        return ManhuajuAgentPipeline(
            script_analyzer=bundle.manhuaju_script_analyzer,
            material_designer=bundle.manhuaju_material_designer,
            video_generator=bundle.manhuaju_video_generator,
            video_composer=bundle.manhuaju_video_composer,
            output_root=Path(
                getattr(bundle, "manhuaju_output_root", "./api_data/manhuaju_agent")
            ),
        )
    return ManhuajuAgentPipeline.mock(
        output_root=Path(getattr(bundle, "manhuaju_output_root", "./api_data/manhuaju_agent"))
    )
