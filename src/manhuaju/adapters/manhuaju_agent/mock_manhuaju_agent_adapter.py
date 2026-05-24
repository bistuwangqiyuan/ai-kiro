"""Mock adapter for the 火山「短剧漫剧 Agent」4-step pipeline.

无网络依赖，CI/单测/离线开发使用。所有方法返回与官方 ``resp_data`` 字段
一一对应的 Pydantic 模型，数据取自《藏在奶茶里的戒指》官方示例 fixture。
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from manhuaju.adapters.manhuaju_agent.schemas import (
    AppearanceInfo,
    AppearanceNodeDetail,
    AppearanceTree,
    CharacterAsset,
    CharacterDetail,
    CoreElement,
    EpisodeAsset,
    Location,
    MaterialDesignResult,
    Role,
    SceneAsset,
    ScriptAnalysisResult,
    ScriptDetail,
    ScriptSettings,
    ShotResult,
    StoryboardBrief,
    StoryboardDetail,
    TagInfo,
    VideoCompositionResult,
    VideoGenerationResult,
    VoiceInfo,
)


def _new_thread_id() -> str:
    return f"ark_mock_{uuid.uuid4().hex[:16]}"


def _new_assets_id() -> str:
    return f"ark_mock_{uuid.uuid4().hex[:12]}"


class MockManhuajuAgentAdapter:
    """统一 mock：实现 4 个适配器的方法名签名，离线返回真实结构数据。"""

    name = "MockManhuajuAgentAdapter"
    provider = "mock_manhuaju_agent"

    def __init__(self, artefacts_root: Path | None = None) -> None:
        self.artefacts_root = artefacts_root or Path("./api_data/_mock_manhuaju")
        self.artefacts_root.mkdir(parents=True, exist_ok=True)
        self._thread_id = _new_thread_id()
        self._assets_id = _new_assets_id()

    # ===== Stage 1 =====
    def analyze(
        self,
        *,
        file_url: str,  # noqa: ARG002
        visual_style: str = "真人写实, 电影风格, 冷色调,都市女频",
        video_ratio: str = "16:9",
        file_type: str = "docx",  # noqa: ARG002
        file_name: str | None = None,  # noqa: ARG002
        req_key: str | None = None,  # noqa: ARG002
    ) -> ScriptAnalysisResult:
        time.sleep(0.005)
        return ScriptAnalysisResult(
            thread_id=self._thread_id,
            assets_id=self._assets_id,
            status="Success",
            charge_count=3,
            script_detail=ScriptDetail(
                core_element=CoreElement(
                    core_setting="都市求婚",
                    time="当代",
                    main_character="许知夏 / 陈屿",
                    location="奶茶店、公园许愿池",
                    core_plot="陈屿在两人常去的奶茶店向许知夏求婚",
                    perspective="第三人称限知视角",
                    summary="《藏在奶茶里的戒指》——一对青年情侣的浪漫求婚故事",
                    style="温暖治愈、轻松日常",
                    background="都市青年生活",
                    episode_count=3,
                    frequency_category="都市女频",
                ),
                settings=ScriptSettings(visual_style=visual_style, video_ratio=video_ratio),
                character_assets=[
                    CharacterAsset(
                        character_id="C1",
                        character_name="陈屿",
                        character_asset_id="char_mock_C1",
                        is_main_character=True,
                        episode_asset_ids=["ep_mock_1", "ep_mock_2", "ep_mock_3"],
                    ),
                    CharacterAsset(
                        character_id="C2",
                        character_name="许知夏",
                        character_asset_id="char_mock_C2",
                        is_main_character=True,
                        episode_asset_ids=["ep_mock_1", "ep_mock_2", "ep_mock_3"],
                    ),
                ],
                scene_assets=[
                    SceneAsset(scene_asset_id="sc_mock_naicha", episode_asset_ids=["ep_mock_1"]),
                    SceneAsset(scene_asset_id="sc_mock_park", episode_asset_ids=["ep_mock_2"]),
                ],
                episode_assets=[
                    EpisodeAsset(
                        episode_id="1",
                        episode_name="重逢的奶茶杯",
                        episode_title="第一集 重逢",
                        episode_asset_id="ep_mock_1",
                        storyboard_asset_id="sb_mock_1",
                        character_asset_ids=["char_mock_C1", "char_mock_C2"],
                        scene_asset_ids=["sc_mock_naicha"],
                    ),
                    EpisodeAsset(
                        episode_id="2",
                        episode_name="许愿池的回忆",
                        episode_title="第二集 回忆",
                        episode_asset_id="ep_mock_2",
                        storyboard_asset_id="sb_mock_2",
                        character_asset_ids=["char_mock_C1", "char_mock_C2"],
                        scene_asset_ids=["sc_mock_park"],
                    ),
                    EpisodeAsset(
                        episode_id="3",
                        episode_name="戒指与奶茶",
                        episode_title="第三集 求婚",
                        episode_asset_id="ep_mock_3",
                        storyboard_asset_id="sb_mock_3",
                        character_asset_ids=["char_mock_C1", "char_mock_C2"],
                        scene_asset_ids=["sc_mock_naicha"],
                    ),
                ],
                storyboard_briefs=[
                    StoryboardBrief(
                        episode_id="1", episode_asset_id="ep_mock_1", storyboard_asset_id="sb_mock_1"
                    ),
                    StoryboardBrief(
                        episode_id="2", episode_asset_id="ep_mock_2", storyboard_asset_id="sb_mock_2"
                    ),
                    StoryboardBrief(
                        episode_id="3", episode_asset_id="ep_mock_3", storyboard_asset_id="sb_mock_3"
                    ),
                ],
            ),
        )

    # ===== Stage 2 =====
    def design(
        self,
        *,
        assets_id: str | None = None,
        thread_id: str | None = None,
        run_id: str | None = None,  # noqa: ARG002
        req_key: str | None = None,  # noqa: ARG002
    ) -> MaterialDesignResult:
        time.sleep(0.005)
        return MaterialDesignResult(
            thread_id=thread_id or self._thread_id,
            assets_id=assets_id or self._assets_id,
            status="Success",
            charge_count=9,
            character_detail=[
                CharacterDetail(
                    character_id="C1",
                    character_name="陈屿",
                    is_main_character=True,
                    introduction="深情且细心的都市青年，是许知夏的男友。",
                    tag_infos=[
                        TagInfo(
                            name="基础形象",
                            identity=["许知夏的男友", "上班族"],
                            personality="深情专一、细心体贴、有仪式感",
                            background="生活在都市，与女友许知夏交往至少两年",
                            gender="男",
                            age_group="青年",
                            voice_info=VoiceInfo(description="男声，青年音色，温润偏沉"),
                            appearance_info=AppearanceInfo(
                                description="26岁亚洲男性，身高约180cm，海军蓝休闲西装"
                            ),
                            is_core=True,
                        )
                    ],
                    appearance_tree=AppearanceTree(
                        node_id="node_mock_C1",
                        asset_id="char_mock_C1",
                        detail=AppearanceNodeDetail(
                            node_id="root_C1",
                            name="陈屿",
                            stage_name="基础形象",
                            label="基础形象",
                            full_name="陈屿-基础形象-基础形象",
                            is_root=True,
                            appearance="26岁亚洲男性，身高约180cm",
                            voice_info=VoiceInfo(description="男声，青年音色"),
                            body_image_id="img_body_C1",
                            bust_portrait_id="img_bust_C1",
                            body_image_url="https://mock.example.com/C1_body.jpg",
                            bust_portrait_url="https://mock.example.com/C1_bust.jpg",
                            related_episode_num=["1", "2", "3"],
                        ),
                    ),
                ),
                CharacterDetail(
                    character_id="C2",
                    character_name="许知夏",
                    is_main_character=True,
                    introduction="温柔知性的都市女青年，是陈屿的女友。",
                    tag_infos=[
                        TagInfo(
                            name="基础形象",
                            identity=["陈屿的女友"],
                            personality="温柔、细腻、感性",
                            background="都市青年，与陈屿交往至少两年",
                            gender="女",
                            age_group="青年",
                            voice_info=VoiceInfo(description="女声，青年音色，温润偏软"),
                            appearance_info=AppearanceInfo(
                                description="25岁亚洲女性，雾霾蓝针织开衫"
                            ),
                            is_core=True,
                        )
                    ],
                    appearance_tree=AppearanceTree(
                        node_id="node_mock_C2",
                        asset_id="char_mock_C2",
                        detail=AppearanceNodeDetail(
                            node_id="root_C2",
                            name="许知夏",
                            stage_name="基础形象",
                            label="基础形象",
                            full_name="许知夏-基础形象-基础形象",
                            is_root=True,
                            appearance="25岁亚洲女性",
                            voice_info=VoiceInfo(description="女声，青年音色"),
                            body_image_id="img_body_C2",
                            bust_portrait_id="img_bust_C2",
                            body_image_url="https://mock.example.com/C2_body.jpg",
                            bust_portrait_url="https://mock.example.com/C2_bust.jpg",
                            related_episode_num=["1", "2", "3"],
                        ),
                    ),
                ),
            ],
        )

    # ===== Stage 3 =====
    def generate(
        self,
        *,
        assets_id: str | None = None,
        thread_id: str | None = None,
        episode_id: str = "1",
        run_id: str | None = None,  # noqa: ARG002
        budget_tier: str = "M",  # noqa: ARG002
        req_key: str | None = None,  # noqa: ARG002
    ) -> VideoGenerationResult:
        time.sleep(0.005)
        shots = [
            ShotResult(
                shot_id=f"S{i}",
                description=f"分镜 {i}",
                status=3,
                video_url=f"https://mock.example.com/ep{episode_id}_shot{i}.mp4",
                duration=5000,
                width=1280,
                height=720,
                format="mp4",
                size=2_500_000,
                video_asset_id=f"vasset_mock_{episode_id}_{i}",
                model_name="seedance-2.0-fast-720p",
            )
            for i in (1, 2, 3, 4, 5)
        ]
        return VideoGenerationResult(
            thread_id=thread_id or self._thread_id,
            assets_id=assets_id or self._assets_id,
            status="Success",
            charge_count=5,
            storyboard_detail=[
                StoryboardDetail(
                    episode_id=str(episode_id),
                    episode_asset_id=f"ep_mock_{episode_id}",
                    visual_style="真人写实, 电影风格, 冷色调,都市女频",
                    role_list=[
                        Role(
                            role_id="R1",
                            role_name="许知夏-基础形象-基础形象",
                            visual_attributes="25岁亚洲女性",
                            vocal_attributes="女声，青年音色",
                            material_id="mat_R1",
                        ),
                        Role(
                            role_id="R2",
                            role_name="陈屿-基础形象-基础形象",
                            visual_attributes="26岁亚洲男性",
                            vocal_attributes="男声，青年音色",
                            material_id="mat_R2",
                        ),
                    ],
                    location_list=[
                        Location(
                            location_id="L1",
                            location_name="奶茶店",
                            description="温馨小资奶茶店",
                            material_id="mat_L1",
                        )
                    ],
                    shots=shots,
                )
            ],
        )

    def generate_with_retry(self, **kw: Any) -> VideoGenerationResult:
        return self.generate(**kw)

    # ===== Stage 4 =====
    def compose(
        self,
        *,
        assets_id: str | None = None,
        thread_id: str | None = None,
        episode_id: str = "1",
        budget_tier: str = "M",  # noqa: ARG002
        req_key: str | None = None,  # noqa: ARG002
    ) -> VideoCompositionResult:
        time.sleep(0.005)
        return VideoCompositionResult(
            thread_id=thread_id or self._thread_id,
            assets_id=assets_id or self._assets_id,
            run_id=f"mock_compose_{episode_id}",
            status="Success",
            storyboard_asset_id=f"sb_mock_{episode_id}",
            final_video_url=f"https://mock.example.com/final_ep{episode_id}.mp4",
            final_video_cover_url=f"https://mock.example.com/final_ep{episode_id}.jpg",
        )

    def download(self, url: str, dest: Path, *, timeout_s: float = 300) -> Path:  # noqa: ARG002
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_bytes(b"\x00mock-video\x00")
        return dest

    @staticmethod
    def cache_filename(prefix: str, url: str, suffix: str = ".mp4") -> str:
        import hashlib

        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}_{digest}{suffix}"

    @staticmethod
    def gen_run_id(prefix: str = "run") -> str:
        body = uuid.uuid4().hex[:24]
        max_prefix = 32 - 1 - 24
        p = (prefix or "run")[:max_prefix]
        return f"{p}_{body}"[:32]
