"""Unit tests for v2 six-step workflow components."""

from __future__ import annotations

from pathlib import Path

import yaml

from manhuaju.core.review_gate import ReviewGate, ReviewDecision
from manhuaju.core.workflow_config import load_distribution_config, load_workflow_config
from manhuaju.core.workflow_stage import STAGE_ORDER, WorkflowStage
from manhuaju.services.seven_dim_qa import score_episode, score_shot


def test_workflow_stage_order() -> None:
    assert STAGE_ORDER[0] == WorkflowStage.ANALYZE
    assert WorkflowStage.FINE_CUT in STAGE_ORDER
    assert WorkflowStage.DISTRIBUTION in STAGE_ORDER


def test_workflow_config_from_system_yaml() -> None:
    raw = yaml.safe_load(Path("config/system.yaml").read_text(encoding="utf-8"))
    wf = load_workflow_config(raw)
    dist = load_distribution_config(raw)
    assert wf.mode == "autopilot"
    assert wf.candidates_per_shot == 3
    assert dist.default_platform == "douyin"


def test_style_presets_count() -> None:
    presets = yaml.safe_load(Path("config/style-presets.yaml").read_text(encoding="utf-8"))
    assert len(presets) >= 6


def test_seven_dim_qa_scores() -> None:
    shot = {
        "shot_id": "sh01",
        "prompt_brief": {"clauses": [f"c{i}" for i in range(10)]},
    }
    render = {"shot_id": "sh01", "degraded": False}
    scores = score_shot(shot=shot, render=render, style_sha="abc123")
    assert len(scores) == 7
    ep = score_episode(
        storyboard={"shots": [shot]},
        renders=[render],
        style_sha="abc123",
    )
    assert "dimensions" in ep
    assert ep["pass_all"] is True


def test_review_gate_supervised() -> None:
    gate = ReviewGate(mode="supervised")
    assert gate.should_wait() is True
    assert gate.is_release_allowed("p1", "ep01") is False
    gate.apply("p1", "ep01", "approve")
    assert gate.status("p1", "ep01") == ReviewDecision.APPROVED
    assert gate.is_release_allowed("p1", "ep01") is True
