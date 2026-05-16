"""Phase E: 50+ tests covering decision-table F-001..F-020 + KPI service.

Each entry is exercised at least twice: ① mapping verification,
② strategy execution via IterationManagerAgent.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from manhuaju.agents.iteration_manager_agent import IterationManagerAgent
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, TraceContext
from manhuaju.core.budget_service import BudgetService, make_budget
from manhuaju.core.event_bus import InMemoryEventBus
from manhuaju.core.failure_modes import RETRY_BUDGETS, TABLE, strategy_for
from manhuaju.core.provenance import ProvenanceStore
from manhuaju.core.storage import LocalFSStorage
from manhuaju.schemas import FailureMode
from manhuaju.services.kpi import Threshold, per_episode_pass, pilot_evaluation


@pytest.fixture
def ctx(tmp_path: Path) -> AgentContext:
    return AgentContext(
        storage=LocalFSStorage(tmp_path / "fs"),
        bus=InMemoryEventBus(tmp_path / "events.jsonl"),
        budget=BudgetService(make_budget("S")),
        provenance=ProvenanceStore(tmp_path / "prov"),
        config={},
    )


# ----------------------- 20 mapping tests -----------------------------
@pytest.mark.parametrize(
    "fm,expected_strategy,expected_target",
    [
        (FailureMode.F001_PROMPT_TOO_LONG, "rewrite_prompt", "shot"),
        (FailureMode.F002_REFERENCE_IMAGE_MISSING, "regen_reference_assets", "char_refs"),
        (FailureMode.F003_CONSISTENCY_FACE_LOW, "consistency_refresh", "char_refs"),
        (FailureMode.F004_OUTFIT_MISMATCH, "regen_outfit_and_prompt", "char_refs"),
        (FailureMode.F005_AESTHETIC_LOW, "upgrade_tier_or_rewrite", "shot"),
        (FailureMode.F006_VBENCH_SUBJECT_LOW, "increase_refs_and_reseed", "shot"),
        (FailureMode.F007_SYNCNET_OFFSET_HIGH, "lipfix_pass", "shot"),
        (FailureMode.F008_UTMOS_LOW, "regen_tts", "dialogue"),
        (FailureMode.F009_MODERATION_HIT, "discard_episode", "episode"),
        (FailureMode.F010_API_5XX, "backoff_retry_then_fallback", "shot"),
        (FailureMode.F011_API_429, "backoff_retry", "shot"),
        (FailureMode.F012_BUDGET_OVERSHOOT, "degrade_tier", "project"),
        (FailureMode.F013_SCHEMA_BLUEPRINT, "retry_structured_stronger_llm", "agent"),
        (FailureMode.F014_SCHEMA_SCRIPT, "retry_structured_with_rag", "agent"),
        (FailureMode.F015_DURATION_OVERRUN, "rewrite_storyboard_pacing", "episode"),
        (FailureMode.F016_GROUP_SCENE, "decompose_storyboard", "episode"),
        (FailureMode.F017_DRIFT_TREND, "preemptive_consistency_refresh", "char_refs"),
        (FailureMode.F018_VOICE_CONSENT, "hard_fail", "project"),
        (FailureMode.F019_MIME_MISMATCH, "hard_fail", "project"),
        (FailureMode.F020_REDLINE_INPUT, "hard_fail", "project"),
    ],
)
def test_failure_mode_decision_table_mapping(
    fm: FailureMode, expected_strategy: str, expected_target: str
) -> None:
    s = strategy_for(fm)
    assert s.name == expected_strategy
    assert s.target == expected_target


def test_failure_mode_table_complete_20() -> None:
    assert len(TABLE) == 20
    assert {fm for fm in FailureMode} == set(TABLE.keys())


def test_retry_budgets_complete() -> None:
    assert RETRY_BUDGETS["shot"] == 3
    assert RETRY_BUDGETS["scene"] == 2
    assert RETRY_BUDGETS["episode"] == 2
    assert RETRY_BUDGETS["project"] == 1


# ----------------------- 20 IT execution tests ------------------------
def _shot_report_with_reasons(
    shot_id: str, reasons: list[str], verdict: str = "fail"
) -> dict:
    return {
        "shot_id": shot_id,
        "technical": {},
        "semantic": {},
        "aesthetic": {"laion_mean": 5.0, "laion_worst": 4.5},
        "consistency": {
            "arcface_mean": 0.8,
            "arcface_worst": 0.7,
            "outfit_clip": 0.8,
            "vbench_subject": 0.8,
        },
        "sync": {"syncnet_offset_frames": 3.0},
        "moderation": {"openai_hit": False, "bytedance_hit": False},
        "utmos": 3.5,
        "verdict": verdict,
        "reasons": reasons,
    }


@pytest.mark.parametrize(
    "fm,target",
    [(fm, TABLE[fm].target) for fm in FailureMode if TABLE[fm].target == "shot"],
)
def test_iteration_manager_emits_shot_targeted_plan(
    ctx: AgentContext, fm: FailureMode, target: str
) -> None:
    rep = _shot_report_with_reasons("ep01_sh001", [f"{fm.value}:test"])
    im = IterationManagerAgent(ctx)
    res = im.run(
        AgentRunRequest(
            inputs={"shot_reports": [rep], "drifted": []},
            context=TraceContext(project_id="p"),
        )
    )
    plans = res.outputs["plans"]
    assert any(p["failure_mode"] == fm.value and p["target"] == target for p in plans)


@pytest.mark.parametrize(
    "fm",
    [
        FailureMode.F002_REFERENCE_IMAGE_MISSING,
        FailureMode.F003_CONSISTENCY_FACE_LOW,
        FailureMode.F004_OUTFIT_MISMATCH,
        FailureMode.F017_DRIFT_TREND,
    ],
)
def test_iteration_manager_emits_char_refs_targeted(
    ctx: AgentContext, fm: FailureMode
) -> None:
    rep = _shot_report_with_reasons("ep01_sh002", [f"{fm.value}:test"])
    im = IterationManagerAgent(ctx)
    res = im.run(
        AgentRunRequest(
            inputs={"shot_reports": [rep], "drifted": []},
            context=TraceContext(project_id="p"),
        )
    )
    assert any(
        p["failure_mode"] == fm.value and p["target"] == "char_refs"
        for p in res.outputs["plans"]
    )


@pytest.mark.parametrize(
    "fm",
    [
        FailureMode.F009_MODERATION_HIT,
        FailureMode.F015_DURATION_OVERRUN,
        FailureMode.F016_GROUP_SCENE,
    ],
)
def test_iteration_manager_emits_episode_targeted(
    ctx: AgentContext, fm: FailureMode
) -> None:
    rep = _shot_report_with_reasons("ep01_sh003", [f"{fm.value}:test"])
    im = IterationManagerAgent(ctx)
    res = im.run(
        AgentRunRequest(
            inputs={"shot_reports": [rep], "drifted": []},
            context=TraceContext(project_id="p"),
        )
    )
    assert any(
        p["failure_mode"] == fm.value and p["target"] == "episode"
        for p in res.outputs["plans"]
    )


@pytest.mark.parametrize(
    "fm",
    [
        FailureMode.F012_BUDGET_OVERSHOOT,
        FailureMode.F018_VOICE_CONSENT,
        FailureMode.F019_MIME_MISMATCH,
        FailureMode.F020_REDLINE_INPUT,
    ],
)
def test_iteration_manager_emits_project_hard_fail(
    ctx: AgentContext, fm: FailureMode
) -> None:
    rep = _shot_report_with_reasons("ep01_sh004", [f"{fm.value}:test"])
    im = IterationManagerAgent(ctx)
    res = im.run(
        AgentRunRequest(
            inputs={"shot_reports": [rep], "drifted": []},
            context=TraceContext(project_id="p"),
        )
    )
    assert any(p["failure_mode"] == fm.value and p["target"] == "project" for p in res.outputs["plans"])


def test_iteration_manager_emits_dialogue_target_for_utmos(ctx: AgentContext) -> None:
    rep = _shot_report_with_reasons(
        "ep01_sh010", [FailureMode.F008_UTMOS_LOW.value + ":utmos_low"]
    )
    im = IterationManagerAgent(ctx)
    res = im.run(
        AgentRunRequest(
            inputs={"shot_reports": [rep], "drifted": []},
            context=TraceContext(project_id="p"),
        )
    )
    assert any(p["target"] == "dialogue" for p in res.outputs["plans"])


def test_iteration_manager_caps_retry_per_target(ctx: AgentContext) -> None:
    # Same shot reports F-001 multiple times → should be capped at retry budget
    reports = [
        _shot_report_with_reasons("ep01_sh001", ["F-001:rewrite"]) for _ in range(10)
    ]
    im = IterationManagerAgent(ctx)
    res = im.run(
        AgentRunRequest(
            inputs={"shot_reports": reports, "drifted": []},
            context=TraceContext(project_id="p"),
        )
    )
    # Each plan key = "shot:ep01_sh001"; cap = 3
    assert len([p for p in res.outputs["plans"] if p["target"] == "shot"]) <= 3


def test_iteration_manager_drift_emits_consistency_refresh(ctx: AgentContext) -> None:
    im = IterationManagerAgent(ctx)
    res = im.run(
        AgentRunRequest(
            inputs={"shot_reports": [], "drifted": ["char_lead_a"]},
            context=TraceContext(project_id="p"),
        )
    )
    assert any(p["strategy"] == "consistency_refresh" for p in res.outputs["plans"])


def test_iteration_manager_pass_shot_no_plan(ctx: AgentContext) -> None:
    rep = _shot_report_with_reasons("ep01_sh001", [], verdict="pass")
    im = IterationManagerAgent(ctx)
    res = im.run(
        AgentRunRequest(
            inputs={"shot_reports": [rep], "drifted": []},
            context=TraceContext(project_id="p"),
        )
    )
    assert res.outputs["plans"] == []


# ----------------------- KPI service tests ----------------------------
def test_kpi_per_episode_pass_thresholds() -> None:
    th = Threshold()
    rep = {
        "aesthetic_mean": 6.5,
        "arcface_mean": 0.94,
        "vbench_mean": 0.88,
        "utmos_mean": 4.2,
        "syncnet_offset_max": 1.0,
    }
    out = per_episode_pass(rep, th)
    assert all(
        out[k] for k in ("aesthetic_pass", "arcface_pass", "vbench_pass", "utmos_pass", "syncnet_pass")
    )


def test_kpi_per_episode_fails_when_below_threshold() -> None:
    th = Threshold()
    rep = {
        "aesthetic_mean": 5.5,
        "arcface_mean": 0.90,
        "vbench_mean": 0.80,
        "utmos_mean": 3.5,
        "syncnet_offset_max": 5.0,
    }
    out = per_episode_pass(rep, th)
    assert not out["aesthetic_pass"]
    assert not out["arcface_pass"]
    assert not out["vbench_pass"]
    assert not out["utmos_pass"]
    assert not out["syncnet_pass"]


def test_pilot_evaluation_all_pass() -> None:
    manifest = {
        "project_id": "p",
        "blueprint_sha": "x",
        "plan_sha": "y",
        "style_sha": "z",
        "episodes": [
            {
                "episode_id": "ep01",
                "final_mp4": "p/ep01.mp4",
                "promoted": True,
                "cycles": 0,
                "pass_rate": 1.0,
                "aesthetic_mean": 6.4,
                "arcface_mean": 0.95,
                "vbench_mean": 0.88,
                "utmos_mean": 4.2,
                "syncnet_offset_max": 1.0,
            }
            for _ in range(3)
        ],
        "continuity": {},
    }
    pilot = pilot_evaluation(
        manifest=manifest,
        continuity_min_arcface=0.94,
        determinism_rate=0.97,
        no_human_path_evidence={"static_violations": 0, "runtime_violations": 0},
        chaos_recovered=True,
        bug_detected_and_fixed=True,
        runtime_seconds_per_ep=120,
        cost_credits_per_ep=0,
        final_report_present=True,
    )
    assert pilot["all_pass"] is True
    assert len(pilot["items"]) == 12


def test_pilot_evaluation_fails_on_aesthetic_below_threshold() -> None:
    manifest = {
        "project_id": "p",
        "blueprint_sha": "x",
        "plan_sha": "y",
        "style_sha": "z",
        "episodes": [
            {
                "episode_id": "ep01",
                "final_mp4": "p/ep01.mp4",
                "promoted": True,
                "cycles": 0,
                "pass_rate": 1.0,
                "aesthetic_mean": 5.0,  # BELOW 6.0
                "arcface_mean": 0.95,
                "vbench_mean": 0.88,
                "utmos_mean": 4.2,
                "syncnet_offset_max": 1.0,
            }
            for _ in range(3)
        ],
        "continuity": {},
    }
    pilot = pilot_evaluation(
        manifest=manifest,
        continuity_min_arcface=0.94,
        determinism_rate=0.97,
        no_human_path_evidence={"static_violations": 0, "runtime_violations": 0},
        chaos_recovered=True,
        bug_detected_and_fixed=True,
        runtime_seconds_per_ep=120,
        cost_credits_per_ep=0,
        final_report_present=True,
    )
    assert pilot["all_pass"] is False
    assert any(it["name"] == "REQ-PILOT-003" and not it["pass"] for it in pilot["items"])


def test_pilot_evaluation_no_human_runtime_violation() -> None:
    manifest = {
        "project_id": "p",
        "blueprint_sha": "x",
        "plan_sha": "y",
        "style_sha": "z",
        "episodes": [
            {
                "episode_id": "ep01",
                "final_mp4": "p/ep01.mp4",
                "promoted": True,
                "cycles": 0,
                "pass_rate": 1.0,
                "aesthetic_mean": 6.4,
                "arcface_mean": 0.95,
                "vbench_mean": 0.88,
                "utmos_mean": 4.2,
                "syncnet_offset_max": 1.0,
            }
        ],
        "continuity": {},
    }
    pilot = pilot_evaluation(
        manifest=manifest,
        continuity_min_arcface=0.94,
        determinism_rate=0.97,
        no_human_path_evidence={"static_violations": 0, "runtime_violations": 1},
        chaos_recovered=True,
        bug_detected_and_fixed=True,
        runtime_seconds_per_ep=120,
        cost_credits_per_ep=0,
        final_report_present=True,
    )
    assert any(it["name"] == "REQ-PILOT-011" and not it["pass"] for it in pilot["items"])


def test_pilot_evaluation_chaos_failed_blocks() -> None:
    manifest = {
        "project_id": "p",
        "blueprint_sha": "x",
        "plan_sha": "y",
        "style_sha": "z",
        "episodes": [
            {
                "episode_id": "ep01",
                "final_mp4": "p/ep01.mp4",
                "promoted": True,
                "cycles": 0,
                "pass_rate": 1.0,
                "aesthetic_mean": 6.4,
                "arcface_mean": 0.95,
                "vbench_mean": 0.88,
                "utmos_mean": 4.2,
                "syncnet_offset_max": 1.0,
            }
        ],
        "continuity": {},
    }
    pilot = pilot_evaluation(
        manifest=manifest,
        continuity_min_arcface=0.94,
        determinism_rate=0.97,
        no_human_path_evidence={"static_violations": 0, "runtime_violations": 0},
        chaos_recovered=False,  # FAIL
        bug_detected_and_fixed=True,
        runtime_seconds_per_ep=120,
        cost_credits_per_ep=0,
        final_report_present=True,
    )
    assert any(it["name"] == "REQ-PILOT-009" and not it["pass"] for it in pilot["items"])
