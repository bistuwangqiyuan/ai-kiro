"""Pydantic v2 schemas for the 火山「短剧漫剧 Agent」OpenAPI 4-step pipeline.

火山官方响应字段为 PascalCase（``CharacterID`` / ``CoreElement`` 等）。
为避免与 Python 关键字 / pydantic 内部命名冲突，我们用 ``snake_case`` 字段名
并通过 ``AliasChoices`` 同时接受 PascalCase（API 响应）与 snake_case（内部
fixture / 测试）输入；``populate_by_name=True`` 让属性访问保持 Pythonic。
"""

from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


_ACRONYMS = {"id", "url", "ai", "ak", "sk", "io", "cv"}


def _pascal(name: str) -> AliasChoices:
    """Return alias choices matching the original snake_case field name plus all
    plausible PascalCase variants used by the 火山 API. We emit BOTH "ID" and
    "Id" forms for ambiguous suffixes since the upstream is inconsistent."""
    parts = name.split("_")
    primary = "".join(p[:1].upper() + p[1:] for p in parts)
    # Build the acronym-aware variant: uppercase known acronyms entirely
    secondary = "".join(p.upper() if p.lower() in _ACRONYMS else p[:1].upper() + p[1:] for p in parts)
    if primary == secondary:
        return AliasChoices(name, primary)
    return AliasChoices(name, primary, secondary)


class _OfficialModel(BaseModel):
    """Base for火山官方响应模型——同时接受 PascalCase 与 snake_case，忽略未知字段。"""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ============================================================
# Stage 1: 剧本解析  ``pippit_shortplay_cvtob_script_analysis``
# ============================================================


class CoreElement(_OfficialModel):
    """``script_detail.CoreElement`` — 剧本核心要素。"""

    core_setting: str = Field(default="", validation_alias=_pascal("core_setting"))
    time: str = Field(default="", validation_alias=_pascal("time"))
    main_character: str = Field(default="", validation_alias=_pascal("main_character"))
    location: str = Field(default="", validation_alias=_pascal("location"))
    core_plot: str = Field(default="", validation_alias=_pascal("core_plot"))
    perspective: str = Field(default="", validation_alias=_pascal("perspective"))
    summary: str = Field(default="", validation_alias=_pascal("summary"))
    style: str = Field(default="", validation_alias=_pascal("style"))
    background: str = Field(default="", validation_alias=_pascal("background"))
    episode_count: int = Field(default=0, validation_alias=_pascal("episode_count"))
    frequency_category: str = Field(default="", validation_alias=_pascal("frequency_category"))


class CharacterAsset(_OfficialModel):
    """``script_detail.CharacterAssets[]`` — 角色形象资产。"""

    character_id: str = Field(validation_alias=_pascal("character_id"))
    character_name: str = Field(default="", validation_alias=_pascal("character_name"))
    character_asset_id: str = Field(default="", validation_alias=_pascal("character_asset_id"))
    appearance_count: int = Field(default=0, validation_alias=_pascal("appearance_count"))
    episode_asset_ids: list[str] = Field(
        default_factory=list, validation_alias=_pascal("episode_asset_ids")
    )
    aliases: list[str] = Field(default_factory=list, validation_alias=_pascal("aliases"))
    is_main_character: bool = Field(default=False, validation_alias=_pascal("is_main_character"))


class SceneAsset(_OfficialModel):
    """``script_detail.SceneAssets[]`` — 场景资产。"""

    scene_asset_id: str = Field(validation_alias=_pascal("scene_asset_id"))
    episode_asset_ids: list[str] = Field(
        default_factory=list, validation_alias=_pascal("episode_asset_ids")
    )


class EpisodeAsset(_OfficialModel):
    """``script_detail.EpisodeAssets[]`` — 单集资产指针。"""

    episode_id: str = Field(validation_alias=_pascal("episode_id"))
    episode_name: str = Field(default="", validation_alias=_pascal("episode_name"))
    episode_title: str = Field(default="", validation_alias=_pascal("episode_title"))
    episode_asset_id: str = Field(default="", validation_alias=_pascal("episode_asset_id"))
    storyboard_asset_id: str = Field(default="", validation_alias=_pascal("storyboard_asset_id"))
    character_asset_ids: list[str] = Field(
        default_factory=list, validation_alias=_pascal("character_asset_ids")
    )
    scene_asset_ids: list[str] = Field(
        default_factory=list, validation_alias=_pascal("scene_asset_ids")
    )
    episode_synopsis_asset_id: str = Field(
        default="", validation_alias=_pascal("episode_synopsis_asset_id")
    )


class StoryboardBrief(_OfficialModel):
    """``script_detail.StoryboardBriefs[]``"""

    episode_id: str = Field(validation_alias=_pascal("episode_id"))
    episode_asset_id: str = Field(default="", validation_alias=_pascal("episode_asset_id"))
    storyboard_asset_id: str = Field(default="", validation_alias=_pascal("storyboard_asset_id"))


class ScriptSettings(_OfficialModel):
    visual_style: str = Field(default="", validation_alias=_pascal("visual_style"))
    video_ratio: str = Field(default="16:9", validation_alias=_pascal("video_ratio"))


class StageStatus(_OfficialModel):
    status: int = Field(default=0, validation_alias=_pascal("status"))
    message: str = Field(default="", validation_alias=_pascal("message"))


class ScriptDetail(_OfficialModel):
    """``resp_data.script_detail``."""

    overview_asset_id: str = Field(default="", validation_alias=_pascal("overview_asset_id"))
    script_asset_id: str = Field(default="", validation_alias=_pascal("script_asset_id"))
    core_element: CoreElement = Field(
        default_factory=CoreElement, validation_alias=_pascal("core_element")
    )
    settings: ScriptSettings = Field(
        default_factory=ScriptSettings, validation_alias=_pascal("settings")
    )
    character_assets: list[CharacterAsset] = Field(
        default_factory=list, validation_alias=_pascal("character_assets")
    )
    scene_assets: list[SceneAsset] = Field(
        default_factory=list, validation_alias=_pascal("scene_assets")
    )
    episode_assets: list[EpisodeAsset] = Field(
        default_factory=list, validation_alias=_pascal("episode_assets")
    )
    storyboard_briefs: list[StoryboardBrief] = Field(
        default_factory=list, validation_alias=_pascal("storyboard_briefs")
    )
    stage_status_map: dict[str, StageStatus] = Field(
        default_factory=dict, validation_alias=_pascal("stage_status_map")
    )


class ScriptAnalysisResult(_OfficialModel):
    """剧本解析完整业务返回。"""

    thread_id: str
    assets_id: str
    status: str = ""
    script_detail: ScriptDetail = Field(default_factory=ScriptDetail)
    charge_count: int = 0

    @property
    def episode_ids(self) -> list[str]:
        return [ep.episode_id for ep in self.script_detail.episode_assets]


# ============================================================
# Stage 2: 图片/素材生成  ``pippit_shortplay_cvtob_material_design``
# ============================================================


class VoiceInfo(_OfficialModel):
    description: str = Field(default="", validation_alias=_pascal("description"))


class AppearanceInfo(_OfficialModel):
    description: str = Field(default="", validation_alias=_pascal("description"))


class TagInfo(_OfficialModel):
    name: str = Field(default="", validation_alias=_pascal("name"))
    identity: list[str] = Field(default_factory=list, validation_alias=_pascal("identity"))
    personality: str = Field(default="", validation_alias=_pascal("personality"))
    background: str = Field(default="", validation_alias=_pascal("background"))
    gender: str = Field(default="", validation_alias=_pascal("gender"))
    age_group: str = Field(default="", validation_alias=_pascal("age_group"))
    voice_info: VoiceInfo = Field(
        default_factory=VoiceInfo, validation_alias=_pascal("voice_info")
    )
    appearance_info: AppearanceInfo = Field(
        default_factory=AppearanceInfo, validation_alias=_pascal("appearance_info")
    )
    is_core: bool = Field(default=False, validation_alias=_pascal("is_core"))


class AppearanceNodeDetail(_OfficialModel):
    node_id: str = Field(default="", validation_alias=_pascal("node_id"))
    name: str = Field(default="", validation_alias=_pascal("name"))
    stage_name: str = Field(default="", validation_alias=_pascal("stage_name"))
    label: str = Field(default="", validation_alias=_pascal("label"))
    full_name: str = Field(default="", validation_alias=_pascal("full_name"))
    is_root: bool = Field(default=False, validation_alias=_pascal("is_root"))
    appearance: str = Field(default="", validation_alias=_pascal("appearance"))
    voice_info: VoiceInfo = Field(
        default_factory=VoiceInfo, validation_alias=_pascal("voice_info")
    )
    body_image_id: str = Field(default="", validation_alias=_pascal("body_image_id"))
    bust_portrait_id: str = Field(default="", validation_alias=_pascal("bust_portrait_id"))
    body_image_url: str = Field(default="", validation_alias=_pascal("body_image_url"))
    bust_portrait_url: str = Field(default="", validation_alias=_pascal("bust_portrait_url"))
    related_episode_num: list[str] = Field(
        default_factory=list, validation_alias=_pascal("related_episode_num")
    )


class AppearanceTree(_OfficialModel):
    node_id: str = Field(default="", validation_alias=_pascal("node_id"))
    asset_id: str = Field(default="", validation_alias=_pascal("asset_id"))
    detail: AppearanceNodeDetail = Field(
        default_factory=AppearanceNodeDetail, validation_alias=_pascal("detail")
    )


class CharacterDetail(_OfficialModel):
    """``resp_data.character_detail[]``"""

    character_id: str = Field(validation_alias=_pascal("character_id"))
    character_name: str = Field(default="", validation_alias=_pascal("character_name"))
    is_main_character: bool = Field(default=False, validation_alias=_pascal("is_main_character"))
    introduction: str = Field(default="", validation_alias=_pascal("introduction"))
    tag_infos: list[TagInfo] = Field(default_factory=list, validation_alias=_pascal("tag_infos"))
    appearance_tree: AppearanceTree = Field(
        default_factory=AppearanceTree, validation_alias=_pascal("appearance_tree")
    )

    @property
    def primary_body_image_url(self) -> str:
        return self.appearance_tree.detail.body_image_url

    @property
    def primary_bust_portrait_url(self) -> str:
        return self.appearance_tree.detail.bust_portrait_url


class MaterialDesignResult(_OfficialModel):
    """图片/素材生成完整业务返回。"""

    thread_id: str
    assets_id: str
    status: str = ""
    character_detail: list[CharacterDetail] = Field(default_factory=list)
    charge_count: int = 0


# ============================================================
# Stage 3: 视频生成  ``pippit_shortplay_cvtob_video_generate_{fast,pro}720p``
# ============================================================


class Role(_OfficialModel):
    role_id: str = Field(validation_alias=_pascal("role_id"))
    role_name: str = Field(default="", validation_alias=_pascal("role_name"))
    visual_attributes: str = Field(default="", validation_alias=_pascal("visual_attributes"))
    vocal_attributes: str = Field(default="", validation_alias=_pascal("vocal_attributes"))
    material_id: str = Field(default="", validation_alias=_pascal("material_id"))


class Location(_OfficialModel):
    location_id: str = Field(validation_alias=_pascal("location_id"))
    location_name: str = Field(default="", validation_alias=_pascal("location_name"))
    description: str = Field(default="", validation_alias=_pascal("description"))
    material_id: str = Field(default="", validation_alias=_pascal("material_id"))


class ShotStatusEntry(_OfficialModel):
    run_id: str = Field(default="", validation_alias=_pascal("run_id"))
    status: int = Field(default=0, validation_alias=_pascal("status"))


class ShotResult(_OfficialModel):
    """单个分镜视频。"""

    shot_id: str = Field(validation_alias=_pascal("shot_id"))
    description: str = Field(default="", validation_alias=_pascal("description"))
    status: int = Field(default=0, validation_alias=_pascal("status"))
    video_url: str = Field(default="", validation_alias=_pascal("video_url"))
    content_length: str = Field(default="", validation_alias=_pascal("content_length"))
    duration: int = Field(default=0, validation_alias=_pascal("duration"))
    model_name: str = Field(default="", validation_alias=_pascal("model_name"))
    location_id_list: list[str] = Field(
        default_factory=list, validation_alias=_pascal("location_id_list")
    )
    version: int = Field(default=0, validation_alias=_pascal("version"))
    width: int = Field(default=0, validation_alias=_pascal("width"))
    height: int = Field(default=0, validation_alias=_pascal("height"))
    format: str = Field(default="", validation_alias=_pascal("format"))
    size: int = Field(default=0, validation_alias=_pascal("size"))
    video_asset_id: str = Field(default="", validation_alias=_pascal("video_asset_id"))

    @property
    def is_done(self) -> bool:
        return self.status == 3 and bool(self.video_url)

    @property
    def is_failed(self) -> bool:
        return self.status in (4, 5)


class StoryboardDetail(_OfficialModel):
    """``resp_data.storyboard_detail[]`` — 单集分镜详情。"""

    episode_id: str = Field(validation_alias=_pascal("episode_id"))
    episode_asset_id: str = Field(default="", validation_alias=_pascal("episode_asset_id"))
    visual_style: str = Field(default="", validation_alias=_pascal("visual_style"))
    role_list: list[Role] = Field(default_factory=list, validation_alias=_pascal("role_list"))
    location_list: list[Location] = Field(
        default_factory=list, validation_alias=_pascal("location_list")
    )
    script_status: int = Field(default=0, validation_alias=_pascal("script_status"))
    shot_status_map: list[dict[str, list[ShotStatusEntry]]] = Field(
        default_factory=list, validation_alias=_pascal("shot_status_map")
    )
    shots: list[ShotResult] = Field(default_factory=list, validation_alias=_pascal("shots"))

    @property
    def all_shots_done(self) -> bool:
        return bool(self.shots) and all(s.is_done for s in self.shots)

    @property
    def failed_shots(self) -> list[ShotResult]:
        return [s for s in self.shots if s.is_failed]


class VideoGenerationResult(_OfficialModel):
    """视频生成完整业务返回。"""

    thread_id: str
    assets_id: str
    status: str = ""
    storyboard_detail: list[StoryboardDetail] = Field(default_factory=list)
    charge_count: int = 0

    def episode(self, episode_id: str) -> StoryboardDetail | None:
        for sb in self.storyboard_detail:
            if sb.episode_id == episode_id:
                return sb
        return None


# ============================================================
# Stage 4: 视频合成  ``pippit_shortplay_cvtob_video_compose_{fast,pro}720p``
# ============================================================


class VideoCompositionResult(_OfficialModel):
    """视频合成完整业务返回。"""

    thread_id: str
    run_id: str = ""
    assets_id: str
    status: str = ""
    storyboard_asset_id: str = ""
    final_video_url: str
    final_video_cover_url: str = ""


# ============================================================
# Aggregate pipeline result
# ============================================================


class EpisodeProduction(_OfficialModel):
    """单集制作产物（pipeline 输出）。"""

    episode_id: str
    episode_title: str = ""
    storyboard: StoryboardDetail | None = None
    composition: VideoCompositionResult | None = None
    final_video_local_path: str = ""
    cost_rmb: float = 0.0
    extra: dict[str, Any] = Field(default_factory=dict)


class ProjectProduction(_OfficialModel):
    """整剧制作产物。"""

    project_id: str
    thread_id: str
    assets_id: str
    script: ScriptAnalysisResult
    materials: MaterialDesignResult
    episodes: list[EpisodeProduction] = Field(default_factory=list)
    total_cost_rmb: float = 0.0
