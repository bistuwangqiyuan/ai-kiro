"""火山「短剧漫剧 Agent」原生 4 步流水线适配器套件 (v5).

提供 4 个独立适配器对应火山官方文档 [docs/85621/2459788](https://www.volcengine.com/docs/85621/2459788?lang=zh)
的完整 OpenAPI 流水线，并以 Pydantic v2 模型承接所有 ``resp_data``。

外部消费者通常调用 ``ManhuajuAgentPipeline``（在 :mod:`manhuaju.pipelines.manhuaju_agent_flow`），
它把 4 步串起来：

    docx_url → ScriptAnalyzer → MaterialDesigner → VideoGenerator → VideoComposer → final_video_url

按 ``budget_tier`` 自动选 ``fast720p`` (M/L 档) 或 ``pro720p`` (H 档) 模型。
"""

from manhuaju.adapters.manhuaju_agent._base import (
    BusinessErrorCode,
    ManhuajuAgentBase,
    ManhuajuAgentError,
    PollTimeoutError,
)
from manhuaju.adapters.manhuaju_agent.material_designer import MaterialDesignerAdapter
from manhuaju.adapters.manhuaju_agent.mock_manhuaju_agent_adapter import MockManhuajuAgentAdapter
from manhuaju.adapters.manhuaju_agent.schemas import (
    CharacterAsset,
    CharacterDetail,
    EpisodeAsset,
    MaterialDesignResult,
    SceneAsset,
    ScriptAnalysisResult,
    ScriptDetail,
    ShotResult,
    StoryboardBrief,
    StoryboardDetail,
    VideoCompositionResult,
    VideoGenerationResult,
)
from manhuaju.adapters.manhuaju_agent.script_analyzer import ScriptAnalyzerAdapter
from manhuaju.adapters.manhuaju_agent.video_composer import VideoComposerAdapter
from manhuaju.adapters.manhuaju_agent.video_generator import VideoGeneratorAdapter

__all__ = [
    "BusinessErrorCode",
    "CharacterAsset",
    "CharacterDetail",
    "EpisodeAsset",
    "ManhuajuAgentBase",
    "ManhuajuAgentError",
    "MaterialDesignResult",
    "MaterialDesignerAdapter",
    "MockManhuajuAgentAdapter",
    "PollTimeoutError",
    "SceneAsset",
    "ScriptAnalysisResult",
    "ScriptAnalyzerAdapter",
    "ScriptDetail",
    "ShotResult",
    "StoryboardBrief",
    "StoryboardDetail",
    "VideoComposerAdapter",
    "VideoCompositionResult",
    "VideoGenerationResult",
    "VideoGeneratorAdapter",
]
