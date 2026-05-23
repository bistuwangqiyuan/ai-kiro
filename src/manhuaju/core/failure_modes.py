"""Failure-mode catalog F-001..F-020 + decision table (design §10.3 / requirements appendix C)."""

from __future__ import annotations

from dataclasses import dataclass

from manhuaju.schemas import FailureMode


@dataclass(frozen=True)
class Strategy:
    name: str
    target: str  # one of: shot / scene / episode / project / agent / dialogue / char_refs


# decision table (F-### → strategy)
TABLE: dict[FailureMode, Strategy] = {
    FailureMode.F001_PROMPT_TOO_LONG: Strategy("rewrite_prompt", "shot"),
    FailureMode.F002_REFERENCE_IMAGE_MISSING: Strategy("regen_reference_assets", "char_refs"),
    FailureMode.F003_CONSISTENCY_FACE_LOW: Strategy("consistency_refresh", "char_refs"),
    FailureMode.F004_OUTFIT_MISMATCH: Strategy("regen_outfit_and_prompt", "char_refs"),
    FailureMode.F005_AESTHETIC_LOW: Strategy("upgrade_tier_or_rewrite", "shot"),
    FailureMode.F006_VBENCH_SUBJECT_LOW: Strategy("increase_refs_and_reseed", "shot"),
    FailureMode.F007_SYNCNET_OFFSET_HIGH: Strategy("lipfix_pass", "shot"),
    FailureMode.F008_UTMOS_LOW: Strategy("regen_tts", "dialogue"),
    FailureMode.F009_MODERATION_HIT: Strategy("discard_episode", "episode"),
    FailureMode.F010_API_5XX: Strategy("backoff_retry_then_fallback", "shot"),
    FailureMode.F011_API_429: Strategy("backoff_retry", "shot"),
    FailureMode.F012_BUDGET_OVERSHOOT: Strategy("degrade_tier", "project"),
    FailureMode.F013_SCHEMA_BLUEPRINT: Strategy("retry_structured_stronger_llm", "agent"),
    FailureMode.F014_SCHEMA_SCRIPT: Strategy("retry_structured_with_rag", "agent"),
    FailureMode.F015_DURATION_OVERRUN: Strategy("rewrite_storyboard_pacing", "episode"),
    FailureMode.F016_GROUP_SCENE: Strategy("decompose_storyboard", "episode"),
    FailureMode.F017_DRIFT_TREND: Strategy("preemptive_consistency_refresh", "char_refs"),
    FailureMode.F018_VOICE_CONSENT: Strategy("hard_fail", "project"),
    FailureMode.F019_MIME_MISMATCH: Strategy("hard_fail", "project"),
    FailureMode.F020_REDLINE_INPUT: Strategy("hard_fail", "project"),
    FailureMode.F021_SEVEN_DIM_FAIL: Strategy("local_redraw", "shot"),
    FailureMode.F022_INTENT_MISMATCH: Strategy("prompt_tweak", "shot"),
    FailureMode.F023_STYLE_DRIFT: Strategy("consistency_refresh", "char_refs"),
    FailureMode.F024_LOCAL_REDRAW: Strategy("local_redraw", "shot"),
    FailureMode.F025_PROMPT_TWEAK: Strategy("prompt_tweak", "shot"),
    FailureMode.F026_FULL_RESUBMIT: Strategy("full_resubmit", "shot"),
    FailureMode.F027_SCENE_REF_MISSING: Strategy("regen_reference_assets", "scene"),
    FailureMode.F028_PROP_REF_MISSING: Strategy("regen_reference_assets", "scene"),
    FailureMode.F029_DISTRIBUTION_FAIL: Strategy("backoff_retry", "episode"),
    FailureMode.F030_REVIEW_REJECTED: Strategy("full_resubmit", "episode"),
}


# retry budgets per design §10.4
RETRY_BUDGETS = {"shot": 3, "scene": 2, "episode": 2, "project": 1}


def strategy_for(fm: FailureMode) -> Strategy:
    return TABLE[fm]


# ==================================================================
# v4 Shell 4 重生路由表 — Doubao VLM 检测到的 issue.type → adapter
# 见 tech.md 外壳 4 决策表 + docx 十二节「问题诊断 + 自动修正」
# ==================================================================
# issue.type → (adapter_kind, hint)
#   adapter_kind: xiaoyunque | seedance | wanflf | overlay | discard
#   hint:         传给 adapter 的额外指引
V4_REPAIR_ROUTES: dict[str, tuple[str, str]] = {
    "face_drift": (
        "wanflf",
        "FLF 首末帧锁脸；保留运动连续性",
    ),
    "axis_violation": (
        "seedance",
        "重抽镜头，强约束『保持轴线一致』，禁止越轴",
    ),
    "limb_distortion": (
        "seedance",
        "肢体结构修正：使用更强约束的 negative prompt（多手指、错位、扭曲）",
    ),
    "text_garbled": (
        "overlay",
        "去除 AI 字层后期 ASS 字幕烧入",
    ),
    "style_offshift": (
        "xiaoyunque",
        "强化 style_reference 权重至 1.0，加入风格关键词锁",
    ),
    "intent_mismatch": (
        "xiaoyunque",
        "prompt 重写突出关键动作与情绪",
    ),
    "detail_loss": (
        "xiaoyunque",
        "增加细节关键词与道具特写描述",
    ),
    "color_drift": (
        "xiaoyunque",
        "强约束色板，加入参考图 style_ref",
    ),
}


def repair_route_for(issue_type: str) -> tuple[str, str]:
    """Return (adapter_kind, hint) for a VLM-detected issue type. Defaults to seedance regen."""
    return V4_REPAIR_ROUTES.get(issue_type, ("seedance", "default regen"))
