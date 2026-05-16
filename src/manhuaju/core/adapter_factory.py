"""Adapter factory: returns adapter instances per `mode` from config/system.yaml.

`mode = mock`   → all `Mock*Adapter` (M2 default; offline; deterministic).
`mode = live`   → `Real*Adapter` over network with cost tracking.
`mode = hybrid` → live primary, automatic mock fallback on failure / missing key.

The factory is the single integration point so agents/pipelines DO NOT import
adapter modules directly. This keeps swap-out trivial and lets us unit-test
mode selection without wiring a full pipeline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from manhuaju.core.cost_tracker import CostTracker
from manhuaju.core.provider_settings import ProviderSettings, get_provider_settings
from manhuaju.utils.paths import config_dir


@dataclass
class AdapterBundle:
    """All adapter instances needed by agents and pipelines."""

    mode: str
    llm: Any
    render_primary: Any
    render_fallback: Any
    tts: Any
    music: Any
    qa: Any
    moderation: Any
    embedding: Any
    cost: CostTracker
    settings: ProviderSettings
    config: dict[str, Any]


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
    """Construct an AdapterBundle for `mode` with all adapter artefact roots
    rooted under ``storage_root``.

    Args:
        storage_root: Per-run storage base — adapters write artefacts under
            ``storage_root/_renders``, ``_tts``, ``_music`` etc.
        mode_override: If given, overrides ``system.yaml :: mode``.
        redlines: Used by the moderation adapters for content filtering.
    """
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
    for p in (renders_root, frames_root, tts_root, music_root):
        p.mkdir(parents=True, exist_ok=True)

    # M2 mock adapters always available — used directly for `mock` and as fallback for `hybrid`.
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

    if mode == "mock":
        return AdapterBundle(
            mode="mock",
            llm=mock_llm,
            render_primary=mock_xy,
            render_fallback=mock_sd,
            tts=mock_tts,
            music=mock_music,
            qa=mock_qa,
            moderation=mock_mod,
            embedding=mock_emb,
            cost=cost,
            settings=settings,
            config=cfg,
        )

    if not settings.has_any_llm:
        # Degrade safely: no live LLM credentials available — return mock bundle
        # tagged with the requested mode so callers can detect the degrade.
        return AdapterBundle(
            mode=f"{mode}-degraded",
            llm=mock_llm,
            render_primary=mock_xy,
            render_fallback=mock_sd,
            tts=mock_tts,
            music=mock_music,
            qa=mock_qa,
            moderation=mock_mod,
            embedding=mock_emb,
            cost=cost,
            settings=settings,
            config=cfg,
        )

    # ---- live or hybrid ----
    RealLLMAdapter = _import("manhuaju.adapters.llm.real_llm_adapter", "RealLLMAdapter")
    RealSeedanceAdapter = _import(
        "manhuaju.adapters.render.real_seedance_adapter", "RealSeedanceAdapter"
    )
    RealWanXAdapter = _import("manhuaju.adapters.render.real_wanx_adapter", "RealWanXAdapter")
    RealDashScopeTTSAdapter = _import(
        "manhuaju.adapters.tts.real_dashscope_tts_adapter", "RealDashScopeTTSAdapter"
    )
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

    # Hybrid mode → always graceful fallback. Live mode → also keeps the
    # mock instance ready as a last-resort fallback so a missing or invalid
    # API key never blocks an episode (it just degrades silently).
    fallback = True
    real_llm = RealLLMAdapter(
        settings=settings,
        cost=cost,
        config=live_cfg.get("llm", {}),
        mock_fallback=mock_llm if fallback else None,
    )
    # Primary render speaks the submit/poll surface (mirrors MockXiaoyunqueAdapter).
    # Fallback render speaks the synthesise(...) surface (mirrors MockSeedanceAdapter)
    # — kept as mock in live mode because the synthesise path is the safety net
    # invoked when the primary fails AND we still need to ship a frame.
    primary_kind = (live_cfg.get("video", {}) or {}).get("primary", "dashscope_wanx")
    if env_pk := os.getenv("MANHUAJU_VIDEO_PRIMARY", "").strip():
        primary_kind = env_pk
    video_cfg = dict(live_cfg.get("video", {}) or {})
    # Persist debug dump under storage_root so per-shot prompts are inspectable.
    video_cfg.setdefault("debug_dump_root", str(storage_root / "_video_debug"))
    if primary_kind == "dashscope_wanx":
        real_render_primary: Any = RealWanXAdapter(
            settings=settings,
            cost=cost,
            config=video_cfg,
            artefacts_root=renders_root,
            frames_root=frames_root,
            mock_fallback=mock_xy if fallback else None,
        )
    elif primary_kind == "volcengine_seedance":
        real_render_primary = RealSeedanceAdapter(
            settings=settings,
            cost=cost,
            config=video_cfg,
            artefacts_root=renders_root,
            frames_root=frames_root,
            mock_fallback=mock_xy if fallback else None,
        )
    else:
        real_render_primary = mock_xy
    real_render_fallback: Any = mock_sd

    real_tts = RealDashScopeTTSAdapter(
        settings=settings,
        cost=cost,
        config=live_cfg.get("tts", {}),
        artefacts_root=tts_root,
        mock_fallback=mock_tts if fallback else None,
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

    return AdapterBundle(
        mode=mode,
        llm=real_llm,
        render_primary=real_render_primary,
        render_fallback=real_render_fallback,
        tts=real_tts,
        music=mock_music,  # M3: keep mock music; royalty/licensing concerns
        qa=real_qa,
        moderation=real_mod,
        embedding=real_emb,
        cost=cost,
        settings=settings,
        config=cfg,
    )
