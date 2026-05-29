"""Adapter factory v4 — single integration point for all 5 shells.

`mode = mock`   → all `Mock*Adapter` (M2 default; offline; deterministic).
`mode = live`   → all `Real*Adapter` over network with cost tracking.
`mode = hybrid` → live primary + automatic mock fallback per adapter.

全国产化默认（``MANHUAJU_DOMESTIC_ONLY=true``，叠加在 M3 之上）:
- ★ ``render_primary = volcengine_seedance`` / ``volcengine_xiaoyunque``（Shell 3 核心生产引擎）
- ``image_primary = volcengine_seedream`` + ``image_variant = volcengine_jimeng`` (Shell 2)
- ``llm_primary = volcengine_ark`` (Doubao Seed 1.6，Shell 1 编剧大脑)
- ``vlm_primary = ark_doubao_seed_1_6`` (Shell 4 多模态质检)
- ``face_repair`` 默认关闭（境外 fal.ai 仅 DOMESTIC_ONLY=false 时启用）
- ``music = local_library`` + ``sfx = ffmpeg``（境外 ElevenLabs 仅 DOMESTIC_ONLY=false 时启用）
- ``storage = volcengine_tos`` (跨服务图片 URL)
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from manhuaju.core.cost_tracker import CostTracker
from manhuaju.core.provider_settings import ProviderSettings, get_provider_settings
from manhuaju.utils.paths import config_dir


@dataclass
class AdapterBundle:
    """All adapter instances needed by agents and pipelines (v4)."""

    mode: str
    llm: Any
    llm_native: Any | None = None  # anthropic native (Shell 1)
    render_primary: Any = None
    render_fallback: Any = None
    face_repair: Any | None = None  # fal.ai Wan 2.7 FLF
    image: Any = None
    image_variant: Any | None = None  # Jimeng 4.6
    tts: Any = None
    music: Any = None
    sfx: Any | None = None
    qa: Any = None
    vlm: Any | None = None  # Doubao Seed 1.6
    moderation: Any = None
    embedding: Any = None
    storage_tos: Any | None = None
    # 火山「短剧漫剧 Agent」原生 4 步集成接口（双轨制 M/L 档默认走这套）
    manhuaju_script_analyzer: Any | None = None
    manhuaju_material_designer: Any | None = None
    manhuaju_video_generator: Any | None = None
    manhuaju_video_composer: Any | None = None
    manhuaju_output_root: str = "api_data/manhuaju_agent"
    video_engine: str = "auto"  # auto | xiaoyunque_v2 | manhuaju_agent
    cost: CostTracker = field(default_factory=CostTracker)
    settings: ProviderSettings = field(default_factory=ProviderSettings)
    config: dict[str, Any] = field(default_factory=dict)


def _load_system_config() -> dict[str, Any]:
    path = config_dir() / "system.yaml"
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise ValueError("system.yaml must be a mapping")
    return cfg


def _import(module_path: str, attr: str) -> Any:
    mod = __import__(module_path, fromlist=[attr])
    return getattr(mod, attr)


def build_bundle(
    *,
    storage_root: Path,
    mode_override: str | None = None,
    redlines: list[str] | None = None,
) -> AdapterBundle:
    """Construct an AdapterBundle for `mode`. All adapters rooted under storage_root."""
    cfg = _load_system_config()
    mode = mode_override or str(cfg.get("mode", "mock")).lower()
    if mode not in {"mock", "live", "hybrid"}:
        raise ValueError(f"unknown mode: {mode}")

    cost = CostTracker()
    settings = get_provider_settings()
    live_cfg = cfg.get("live", {}) or {}

    storage_root = Path(storage_root)
    storage_root.mkdir(parents=True, exist_ok=True)
    renders_root = storage_root / "_renders"
    frames_root = storage_root / "_frames"
    tts_root = storage_root / "_tts"
    music_root = storage_root / "_music"
    sfx_root = storage_root / "_sfx"
    images_root = storage_root / "_images"
    for p in (renders_root, frames_root, tts_root, music_root, sfx_root, images_root):
        p.mkdir(parents=True, exist_ok=True)

    # ---- Mock adapters (always available) ----
    MockLLMAdapter = _import("manhuaju.adapters.llm.mock_llm_adapter", "MockLLMAdapter")
    MockXiaoyunqueAdapter = _import(
        "manhuaju.adapters.render.mock_xiaoyunque_adapter", "MockXiaoyunqueAdapter"
    )
    MockSeedanceAdapter = _import(
        "manhuaju.adapters.render.mock_seedance_adapter", "MockSeedanceAdapter"
    )
    MockTTSAdapter = _import("manhuaju.adapters.tts.mock_tts_adapter", "MockTTSAdapter")
    MockMusicAdapter = _import("manhuaju.adapters.music.mock_music_adapter", "MockMusicAdapter")
    MockQAEvaluatorAdapter = _import(
        "manhuaju.adapters.qa.mock_qa_evaluator_adapter", "MockQAEvaluatorAdapter"
    )
    MockModerationAdapter = _import(
        "manhuaju.adapters.moderation.mock_moderation_adapter", "MockModerationAdapter"
    )
    MockEmbeddingAdapter = _import(
        "manhuaju.adapters.embedding.mock_embedding_adapter", "MockEmbeddingAdapter"
    )
    MockImageAdapter = _import("manhuaju.adapters.image.mock_image_adapter", "MockImageAdapter")
    MockSFXAdapter = _import("manhuaju.adapters.sfx.mock_sfx_adapter", "MockSFXAdapter")

    mock_llm = MockLLMAdapter()
    mock_sd = MockSeedanceAdapter(artefacts_root=renders_root, frames_root=frames_root)
    mock_xy = MockXiaoyunqueAdapter(
        artefacts_root=renders_root,
        frames_root=frames_root,
        seedance_fallback=mock_sd,
    )
    mock_tts = MockTTSAdapter(artefacts_root=tts_root)
    mock_music = MockMusicAdapter(artefacts_root=music_root)
    mock_qa = MockQAEvaluatorAdapter()
    mock_mod = MockModerationAdapter(redlines=redlines or [])
    mock_emb = MockEmbeddingAdapter()
    mock_image = MockImageAdapter(artefacts_root=images_root)
    mock_sfx = MockSFXAdapter(artefacts_root=sfx_root)

    MockManhuajuAgentAdapter = _import(
        "manhuaju.adapters.manhuaju_agent.mock_manhuaju_agent_adapter",
        "MockManhuajuAgentAdapter",
    )
    manhuaju_out = (
        (live_cfg.get("video", {}) or {})
        .get("manhuaju_agent", {})
        .get("output_root", "api_data/manhuaju_agent")
    )
    mock_manhuaju = MockManhuajuAgentAdapter(artefacts_root=storage_root / "_manhuaju_agent_mock")

    if mode == "mock":
        return AdapterBundle(
            mode="mock",
            llm=mock_llm,
            llm_native=None,
            render_primary=mock_xy,
            render_fallback=mock_sd,
            face_repair=None,
            image=mock_image,
            image_variant=mock_image,
            tts=mock_tts,
            music=mock_music,
            sfx=mock_sfx,
            qa=mock_qa,
            vlm=None,
            moderation=mock_mod,
            embedding=mock_emb,
            storage_tos=None,
            manhuaju_script_analyzer=mock_manhuaju,
            manhuaju_material_designer=mock_manhuaju,
            manhuaju_video_generator=mock_manhuaju,
            manhuaju_video_composer=mock_manhuaju,
            manhuaju_output_root=manhuaju_out,
            video_engine=str((live_cfg.get("video", {}) or {}).get("engine", "auto")),
            cost=cost,
            settings=settings,
            config=cfg,
        )

    if not settings.has_any_llm:
        return AdapterBundle(
            mode=f"{mode}-degraded",
            llm=mock_llm,
            llm_native=None,
            render_primary=mock_xy,
            render_fallback=mock_sd,
            face_repair=None,
            image=mock_image,
            image_variant=mock_image,
            tts=mock_tts,
            music=mock_music,
            sfx=mock_sfx,
            qa=mock_qa,
            vlm=None,
            moderation=mock_mod,
            embedding=mock_emb,
            storage_tos=None,
            manhuaju_script_analyzer=mock_manhuaju,
            manhuaju_material_designer=mock_manhuaju,
            manhuaju_video_generator=mock_manhuaju,
            manhuaju_video_composer=mock_manhuaju,
            manhuaju_output_root=manhuaju_out,
            video_engine=str((live_cfg.get("video", {}) or {}).get("engine", "auto")),
            cost=cost,
            settings=settings,
            config=cfg,
        )

    # ---- live or hybrid ----
    fallback = True

    # ★ TOS storage — Shell 2/3 都依赖
    TOSStorage = _import("manhuaju.adapters.storage.tos_storage", "TOSStorage")
    tos = TOSStorage(
        settings=settings, prefix=f"manhuaju/{os.getenv('MANHUAJU_ENV', 'dev')}",
        local_fallback_root=images_root / "_tos_local",
    )

    # ---- Shell 1: LLM ----
    RealLLMAdapter = _import("manhuaju.adapters.llm.real_llm_adapter", "RealLLMAdapter")
    real_llm = RealLLMAdapter(
        settings=settings,
        cost=cost,
        config=live_cfg.get("llm", {}),
        mock_fallback=mock_llm if fallback else None,
    )
    anthropic_native: Any | None = None
    if settings.has_anthropic:
        with contextlib.suppress(ImportError):
            RealAnthropicLLMAdapter = _import(
                "manhuaju.adapters.llm.real_anthropic_adapter", "RealAnthropicLLMAdapter"
            )
            anthropic_native = RealAnthropicLLMAdapter(
                settings=settings,
                cost=cost,
                config=live_cfg.get("script", {}),
                mock_fallback=real_llm,
            )

    # ---- Shell 2: Image (Seedream + Jimeng) ----
    image_primary: Any = mock_image
    image_variant: Any = mock_image
    if settings.has_seedream:
        with contextlib.suppress(ImportError):
            RealSeedreamAdapter = _import(
                "manhuaju.adapters.image.real_seedream_adapter", "RealSeedreamAdapter"
            )
            RealJimengAdapter = _import(
                "manhuaju.adapters.image.real_seedream_adapter", "RealJimengAdapter"
            )
            image_primary = RealSeedreamAdapter(
                settings=settings,
                cost=cost,
                config=live_cfg.get("image", {}),
                artefacts_root=images_root,
                tos_storage=tos,
                mock_fallback=mock_image if fallback else None,
            )
            image_variant = RealJimengAdapter(
                settings=settings,
                cost=cost,
                config=live_cfg.get("image", {}),
                artefacts_root=images_root,
                tos_storage=tos,
                mock_fallback=mock_image if fallback else None,
            )
            # 让 image_primary 也能调到 jimeng 做变体（reference_asset_agent 会用）
            image_primary._variant_adapter = image_variant  # noqa: SLF001

    # ---- Shell 3 ★: 小云雀 ----
    primary_kind = (live_cfg.get("video", {}) or {}).get("primary", "volcengine_xiaoyunque")
    if env_pk := os.getenv("MANHUAJU_VIDEO_PRIMARY", "").strip():
        primary_kind = env_pk
    video_cfg = dict(live_cfg.get("video", {}) or {})
    video_cfg.setdefault("debug_dump_root", str(storage_root / "_video_debug"))

    render_primary: Any = mock_xy
    if primary_kind == "volcengine_xiaoyunque" and settings.has_xiaoyunque:
        with contextlib.suppress(ImportError):
            RealXiaoyunqueAdapter = _import(
                "manhuaju.adapters.render.real_xiaoyunque_adapter", "RealXiaoyunqueAdapter"
            )
            render_primary = RealXiaoyunqueAdapter(
                settings=settings,
                cost=cost,
                config=video_cfg,
                artefacts_root=renders_root,
                frames_root=frames_root,
                tos_storage=tos,
                mock_fallback=mock_xy if fallback else None,
            )
    elif primary_kind == "dashscope_wanx":
        with contextlib.suppress(ImportError):
            RealWanXAdapter = _import(
                "manhuaju.adapters.render.real_wanx_adapter", "RealWanXAdapter"
            )
            render_primary = RealWanXAdapter(
                settings=settings,
                cost=cost,
                config=video_cfg,
                artefacts_root=renders_root,
                frames_root=frames_root,
                mock_fallback=mock_xy if fallback else None,
            )
    elif primary_kind == "volcengine_seedance":
        with contextlib.suppress(ImportError):
            RealSeedanceAdapter = _import(
                "manhuaju.adapters.render.real_seedance_adapter", "RealSeedanceAdapter"
            )
            render_primary = RealSeedanceAdapter(
                settings=settings,
                cost=cost,
                config=video_cfg,
                artefacts_root=renders_root,
                frames_root=frames_root,
                mock_fallback=mock_xy if fallback else None,
            )

    # Render fallback — always real Seedance if Ark configured, else mock seedance
    render_fallback: Any = mock_sd
    if settings.volcengine_ark_key:
        with contextlib.suppress(ImportError):
            RealSeedanceAdapter = _import(
                "manhuaju.adapters.render.real_seedance_adapter", "RealSeedanceAdapter"
            )
            render_fallback = RealSeedanceAdapter(
                settings=settings,
                cost=cost,
                config=video_cfg,
                artefacts_root=renders_root,
                frames_root=frames_root,
                mock_fallback=mock_sd if fallback else None,
            )

    # ---- Shell 4: face repair (fal.ai WanFLF) + VLM ----
    face_repair: Any | None = None
    if settings.has_fal:
        with contextlib.suppress(ImportError):
            RealWanFLFAdapter = _import(
                "manhuaju.adapters.render.real_wanflf_adapter", "RealWanFLFAdapter"
            )
            face_repair = RealWanFLFAdapter(
                settings=settings,
                cost=cost,
                config=live_cfg.get("face_repair", {}),
                artefacts_root=renders_root / "flf",
                mock_fallback=mock_xy if fallback else None,
            )

    vlm: Any | None = None
    if settings.has_doubao_vlm:
        with contextlib.suppress(ImportError):
            RealDoubaoVLMAdapter = _import(
                "manhuaju.adapters.vlm.real_doubao_vlm_adapter", "RealDoubaoVLMAdapter"
            )
            vlm = RealDoubaoVLMAdapter(
                settings=settings,
                cost=cost,
                config=live_cfg.get("vlm_qa", {}),
                mock_fallback=None,
            )

    # ---- TTS ----
    RealDashScopeTTSAdapter = _import(
        "manhuaju.adapters.tts.real_dashscope_tts_adapter", "RealDashScopeTTSAdapter"
    )
    real_tts = RealDashScopeTTSAdapter(
        settings=settings,
        cost=cost,
        config=live_cfg.get("tts", {}),
        artefacts_root=tts_root,
        mock_fallback=mock_tts if fallback else None,
    )

    # ---- Shell 5: Music + SFX (国内默认 local_library + ffmpeg；国际版可切 ElevenLabs) ----
    music_adapter: Any = mock_music
    sfx_adapter: Any = mock_sfx
    music_cfg = live_cfg.get("music", {}) or {}
    sfx_cfg = live_cfg.get("sfx", {}) or {}
    music_primary = str(music_cfg.get("primary", "local_library"))
    sfx_primary = str(sfx_cfg.get("primary", "local_synthesis"))

    if music_primary == "local_library":
        with contextlib.suppress(ImportError):
            LocalMusicLibraryAdapter = _import(
                "manhuaju.adapters.music.local_library_adapter",
                "LocalMusicLibraryAdapter",
            )
            music_adapter = LocalMusicLibraryAdapter(
                library_root=str(music_cfg.get("library_root", "assets/bgm")),
                cost_tracker=cost,
            )
    elif music_primary == "elevenlabs" and settings.has_elevenlabs:
        with contextlib.suppress(ImportError):
            RealElevenLabsMusicAdapter = _import(
                "manhuaju.adapters.music.real_elevenlabs_music_adapter",
                "RealElevenLabsMusicAdapter",
            )
            music_adapter = RealElevenLabsMusicAdapter(
                settings=settings,
                cost=cost,
                config=music_cfg,
                artefacts_root=music_root,
                mock_fallback=mock_music if fallback else None,
            )

    if sfx_primary == "local_synthesis":
        # MockSFXAdapter 本身就是 ffmpeg 风格的简单合成，国内默认直接复用
        sfx_adapter = mock_sfx
    elif sfx_primary == "elevenlabs" and settings.has_elevenlabs:
        with contextlib.suppress(ImportError):
            RealElevenLabsSFXAdapter = _import(
                "manhuaju.adapters.sfx.real_elevenlabs_sfx_adapter",
                "RealElevenLabsSFXAdapter",
            )
            sfx_adapter = RealElevenLabsSFXAdapter(
                settings=settings,
                cost=cost,
                config=sfx_cfg,
                artefacts_root=sfx_root,
                mock_fallback=mock_sfx if fallback else None,
            )

    # ---- Moderation + Embedding + QA ----
    RealLLMModerationAdapter = _import(
        "manhuaju.adapters.moderation.real_llm_moderation_adapter",
        "RealLLMModerationAdapter",
    )
    RealDashScopeEmbeddingAdapter = _import(
        "manhuaju.adapters.embedding.real_dashscope_embedding_adapter",
        "RealDashScopeEmbeddingAdapter",
    )
    RealQAProxyAdapter = _import(
        "manhuaju.adapters.qa.real_qa_proxy_adapter", "RealQAProxyAdapter"
    )
    real_mod = RealLLMModerationAdapter(
        llm=real_llm,
        config=live_cfg.get("moderation", {}),
        redlines=redlines,
        mock_fallback=mock_mod if fallback else None,
    )
    real_emb = RealDashScopeEmbeddingAdapter(
        settings=settings,
        cost=cost,
        config=live_cfg.get("embedding", {}),
        mock_fallback=mock_emb if fallback else None,
    )
    real_qa = RealQAProxyAdapter(
        llm=real_llm,
        cost=cost,
        config=live_cfg.get("qa", {}),
        mock_fallback=mock_qa if fallback else None,
    )

    # ---- 火山「短剧漫剧 Agent」原生 4 步集成 OpenAPI（双轨 M/L 档默认） ----
    ma_cfg_root = (live_cfg.get("video", {}) or {}).get("manhuaju_agent", {}) or {}
    if settings.has_xiaoyunque:
        ScriptAnalyzerAdapter = _import(
            "manhuaju.adapters.manhuaju_agent.script_analyzer", "ScriptAnalyzerAdapter"
        )
        MaterialDesignerAdapter = _import(
            "manhuaju.adapters.manhuaju_agent.material_designer", "MaterialDesignerAdapter"
        )
        VideoGeneratorAdapter = _import(
            "manhuaju.adapters.manhuaju_agent.video_generator", "VideoGeneratorAdapter"
        )
        VideoComposerAdapter = _import(
            "manhuaju.adapters.manhuaju_agent.video_composer", "VideoComposerAdapter"
        )
        manhuaju_script = ScriptAnalyzerAdapter(
            settings=settings, cost=cost, config=ma_cfg_root, mock_fallback=mock_manhuaju
        )
        manhuaju_material = MaterialDesignerAdapter(
            settings=settings, cost=cost, config=ma_cfg_root, mock_fallback=mock_manhuaju
        )
        manhuaju_video = VideoGeneratorAdapter(
            settings=settings, cost=cost, config=ma_cfg_root, mock_fallback=mock_manhuaju
        )
        manhuaju_compose = VideoComposerAdapter(
            settings=settings, cost=cost, config=ma_cfg_root, mock_fallback=mock_manhuaju
        )
    else:
        manhuaju_script = mock_manhuaju
        manhuaju_material = mock_manhuaju
        manhuaju_video = mock_manhuaju
        manhuaju_compose = mock_manhuaju

    return AdapterBundle(
        mode=mode,
        llm=real_llm,
        llm_native=anthropic_native,
        render_primary=render_primary,
        render_fallback=render_fallback,
        face_repair=face_repair,
        image=image_primary,
        image_variant=image_variant,
        tts=real_tts,
        music=music_adapter,
        sfx=sfx_adapter,
        qa=real_qa,
        vlm=vlm,
        moderation=real_mod,
        embedding=real_emb,
        storage_tos=tos,
        manhuaju_script_analyzer=manhuaju_script,
        manhuaju_material_designer=manhuaju_material,
        manhuaju_video_generator=manhuaju_video,
        manhuaju_video_composer=manhuaju_compose,
        manhuaju_output_root=str(ma_cfg_root.get("output_root", "api_data/manhuaju_agent")),
        video_engine=str((live_cfg.get("video", {}) or {}).get("engine", "auto")),
        cost=cost,
        settings=settings,
        config=cfg,
    )
