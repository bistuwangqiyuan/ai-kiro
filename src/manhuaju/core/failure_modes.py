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
}


# retry budgets per design §10.4
RETRY_BUDGETS = {"shot": 3, "scene": 2, "episode": 2, "project": 1}


def strategy_for(fm: FailureMode) -> Strategy:
    return TABLE[fm]
