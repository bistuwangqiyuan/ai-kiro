"""End-to-end integration test for the 火山「短剧漫剧 Agent」4-step pipeline.

涵盖：

1. ``MockManhuajuAgentAdapter`` 单适配器接口契约。
2. ``ManhuajuAgentPipeline.mock()`` 端到端 docx → final.mp4。
3. Schemas 反序列化（PascalCase API 响应、snake_case fixture 双向兼容）。
4. ``adapter_factory.build_bundle(mode='mock')`` 装配 manhuaju 适配器。
5. Live 模式由环境变量 ``MANHUAJU_LIVE_TEST=1`` 显式开启（默认 skip）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from manhuaju.adapters.manhuaju_agent import (
    MaterialDesignerAdapter,
    MockManhuajuAgentAdapter,
    ScriptAnalysisResult,
    ScriptAnalyzerAdapter,
    VideoComposerAdapter,
    VideoGeneratorAdapter,
)
from manhuaju.adapters.manhuaju_agent.schemas import (
    MaterialDesignResult,
    ShotResult,
    VideoCompositionResult,
    VideoGenerationResult,
)
from manhuaju.pipelines.manhuaju_agent_flow import ManhuajuAgentPipeline


# ---------------------------------------------------------------- mock contracts


class TestMockAdapter:
    @pytest.fixture
    def mock(self, tmp_path: Path) -> MockManhuajuAgentAdapter:
        return MockManhuajuAgentAdapter(artefacts_root=tmp_path)

    def test_analyze_returns_naicha_fixture(self, mock: MockManhuajuAgentAdapter) -> None:
        r = mock.analyze(file_url="https://example.com/naicha.docx")
        assert isinstance(r, ScriptAnalysisResult)
        assert r.thread_id.startswith("ark_mock_")
        assert r.assets_id.startswith("ark_mock_")
        assert r.charge_count == 3
        assert len(r.script_detail.episode_assets) == 3
        assert r.script_detail.core_element.episode_count == 3
        assert "陈屿" in r.script_detail.core_element.main_character
        assert r.episode_ids == ["1", "2", "3"]

    def test_design_returns_character_detail(self, mock: MockManhuajuAgentAdapter) -> None:
        r = mock.design(assets_id="x", thread_id="t")
        assert isinstance(r, MaterialDesignResult)
        assert len(r.character_detail) == 2
        chen_yu = next(c for c in r.character_detail if c.character_name == "陈屿")
        assert chen_yu.is_main_character
        assert chen_yu.primary_body_image_url.startswith("https://")
        assert chen_yu.primary_bust_portrait_url.startswith("https://")
        assert chen_yu.tag_infos[0].voice_info.description != ""

    def test_generate_returns_5_shots(self, mock: MockManhuajuAgentAdapter) -> None:
        r = mock.generate(assets_id="x", thread_id="t", episode_id="1")
        assert isinstance(r, VideoGenerationResult)
        ep = r.episode("1")
        assert ep is not None
        assert len(ep.shots) == 5
        assert ep.all_shots_done
        assert not ep.failed_shots
        assert all(isinstance(s, ShotResult) for s in ep.shots)
        assert all(s.is_done for s in ep.shots)
        assert ep.shots[0].width == 1280 and ep.shots[0].height == 720

    def test_compose_returns_final_video_url(self, mock: MockManhuajuAgentAdapter) -> None:
        r = mock.compose(assets_id="x", thread_id="t", episode_id="1")
        assert isinstance(r, VideoCompositionResult)
        assert r.final_video_url.startswith("https://mock")
        assert r.final_video_cover_url.startswith("https://mock")
        assert r.storyboard_asset_id != ""

    def test_run_id_generation_under_32_chars(self, mock: MockManhuajuAgentAdapter) -> None:
        for prefix in ("a", "abc", "very_long_prefix_indeed"):
            rid = mock.gen_run_id(prefix)
            assert len(rid) <= 32
            assert rid


# ---------------------------------------------------------------- schema round-trips


class TestSchemaRoundtrip:
    """Both PascalCase (raw API) and snake_case (internal fixture) decode."""

    def test_pascal_case_api_response_decodes(self) -> None:
        # 模拟火山官方接口返回的 PascalCase 字段
        raw_resp_data = json.loads(
            """{
                "thread_id": "ark_3572",
                "assets_id": "ark_1194",
                "status": "Success",
                "script_detail": {
                    "CoreElement": {"CoreSetting": "都市求婚", "EpisodeCount": 3},
                    "Settings": {"VisualStyle": "电影风格", "VideoRatio": "16:9"},
                    "CharacterAssets": [
                        {"CharacterID": "C1", "CharacterName": "陈屿", "IsMainCharacter": true}
                    ],
                    "EpisodeAssets": [
                        {"EpisodeID": "1", "EpisodeName": "重逢", "EpisodeAssetID": "ep_1"}
                    ]
                },
                "charge_count": 3
            }"""
        )
        r = ScriptAnalysisResult.model_validate(raw_resp_data)
        assert r.thread_id == "ark_3572"
        assert r.script_detail.core_element.episode_count == 3
        assert r.script_detail.core_element.core_setting == "都市求婚"
        assert r.script_detail.settings.visual_style == "电影风格"
        assert r.script_detail.character_assets[0].character_name == "陈屿"
        assert r.script_detail.character_assets[0].is_main_character is True
        assert r.script_detail.episode_assets[0].episode_id == "1"

    def test_shot_pascal_case_decodes(self) -> None:
        raw = json.loads(
            '{"ShotID": "S1", "Status": 3, "VideoURL": "https://x/a.mp4",'
            ' "Duration": 5000, "Width": 1280, "Height": 720}'
        )
        s = ShotResult.model_validate(raw)
        assert s.shot_id == "S1"
        assert s.video_url == "https://x/a.mp4"
        assert s.duration == 5000
        assert s.is_done is True

    def test_failed_shot_detected(self) -> None:
        s = ShotResult(shot_id="X", status=4, video_url="")
        assert s.is_failed
        assert not s.is_done


# ---------------------------------------------------------------- e2e mock pipeline


class TestMockPipeline:
    def test_run_project_full_3_episodes(self, tmp_path: Path) -> None:
        pipe = ManhuajuAgentPipeline.mock(output_root=tmp_path)
        proj = pipe.run_project(
            file_url="https://example.com/naicha.docx",
            budget_tier="M",
            visual_style="真人写实",
        )
        assert proj.project_id.startswith("prj_")
        assert proj.thread_id.startswith("ark_mock_")
        assert proj.assets_id.startswith("ark_mock_")
        assert len(proj.materials.character_detail) == 2
        assert len(proj.episodes) == 3
        for i, ep in enumerate(proj.episodes, start=1):
            assert ep.episode_id == str(i)
            assert ep.composition is not None
            assert ep.composition.final_video_url.endswith(f"ep{i}.mp4")
            assert ep.storyboard is not None
            assert len(ep.storyboard.shots) == 5
            assert ep.final_video_local_path != ""
            assert Path(ep.final_video_local_path).exists()
            assert Path(ep.final_video_local_path).stat().st_size > 0

    def test_run_project_max_episodes_limits(self, tmp_path: Path) -> None:
        pipe = ManhuajuAgentPipeline.mock(output_root=tmp_path)
        proj = pipe.run_project(
            file_url="https://example.com/naicha.docx", max_episodes=1
        )
        assert len(proj.episodes) == 1
        assert proj.episodes[0].episode_id == "1"

    def test_skip_compose_only_generates_shots(self, tmp_path: Path) -> None:
        pipe = ManhuajuAgentPipeline.mock(output_root=tmp_path)
        pipe.skip_compose = True
        proj = pipe.run_project(
            file_url="https://example.com/naicha.docx", max_episodes=1
        )
        assert proj.episodes[0].composition is None
        assert proj.episodes[0].storyboard is not None

    def test_run_episode_h_tier_calls_pro(self, tmp_path: Path) -> None:
        """H tier should still work via mock (only req_key differs)."""
        pipe = ManhuajuAgentPipeline.mock(output_root=tmp_path)
        episode = pipe.run_episode(
            assets_id="a", thread_id="t", episode_id="1", budget_tier="H"
        )
        assert episode.composition is not None
        assert episode.composition.final_video_url


# ---------------------------------------------------------------- adapter_factory bundle


class TestAdapterFactoryBundle:
    def test_mock_bundle_has_manhuaju_adapters(self, tmp_path: Path) -> None:
        from manhuaju.core.adapter_factory import build_bundle

        bundle = build_bundle(storage_root=tmp_path, mode_override="mock")
        assert bundle.manhuaju_script_analyzer is not None
        assert bundle.manhuaju_material_designer is not None
        assert bundle.manhuaju_video_generator is not None
        assert bundle.manhuaju_video_composer is not None
        assert type(bundle.manhuaju_script_analyzer).__name__ == "MockManhuajuAgentAdapter"

    def test_factory_pipeline_helper(self, tmp_path: Path) -> None:
        from manhuaju.core.adapter_factory import build_bundle
        from manhuaju.pipelines.manhuaju_agent_flow import build_pipeline_from_bundle

        bundle = build_bundle(storage_root=tmp_path, mode_override="mock")
        pipeline = build_pipeline_from_bundle(bundle)
        proj = pipeline.run_project(
            file_url="https://example.com/naicha.docx", max_episodes=1
        )
        assert proj.episodes[0].composition is not None


# ---------------------------------------------------------------- live mode (opt-in)


@pytest.mark.skipif(
    os.environ.get("MANHUAJU_LIVE_TEST") != "1",
    reason="Set MANHUAJU_LIVE_TEST=1 to run against real Volcengine API",
)
class TestLiveAdapter:
    """Opt-in tests against real Volcengine endpoints.

    Requires:
      - VOLCENGINE_VISUAL_AK / VOLCENGINE_VISUAL_SK in env
      - VOLCENGINE_TOS_* configured + a docx uploaded to TOS
      - 已在控制台开通漫剧 Agent 应用
      - 设置 ``MANHUAJU_TEST_DOCX_URL`` 指向你 TOS 上的 docx 预签名 URL
    """

    @pytest.fixture
    def adapters(self) -> dict:
        from manhuaju.core.cost_tracker import CostTracker
        from manhuaju.core.provider_settings import get_provider_settings

        s = get_provider_settings(refresh=True)
        if not s.has_xiaoyunque:
            pytest.skip("VOLCENGINE_VISUAL_AK/SK not configured")
        cost = CostTracker()
        cfg = {"poll_interval_s": 10, "max_poll_s": 3600}
        return {
            "script": ScriptAnalyzerAdapter(settings=s, cost=cost, config=cfg),
            "material": MaterialDesignerAdapter(settings=s, cost=cost, config=cfg),
            "video": VideoGeneratorAdapter(settings=s, cost=cost, config=cfg),
            "compose": VideoComposerAdapter(settings=s, cost=cost, config=cfg),
        }

    def test_live_script_analysis_smoke(self, adapters: dict) -> None:
        docx = os.environ.get("MANHUAJU_TEST_DOCX_URL")
        if not docx:
            pytest.skip("Set MANHUAJU_TEST_DOCX_URL to run live smoke")
        r = adapters["script"].analyze(file_url=docx, video_ratio="16:9")
        assert r.thread_id
        assert r.assets_id
        assert len(r.script_detail.episode_assets) >= 1
