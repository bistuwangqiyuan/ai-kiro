"""v4 smoke unit tests.

These do not call any external API; everything runs against mock fallbacks
or pure helpers. Used in CI to lock down v4 contracts before live runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_provider_settings_loads_and_redacts(monkeypatch):
    # Anthropic is an overseas provider; it only loads when the全国产化 gate is
    # explicitly disabled. Default deployments stay domestic-only.
    monkeypatch.setenv("MANHUAJU_DOMESTIC_ONLY", "false")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test1234567890abcdef")
    monkeypatch.setenv("VOLCENGINE_VISUAL_AK", "VAK_smoke123456")
    monkeypatch.setenv("VOLCENGINE_VISUAL_SK", "VSK_smoke123456")
    monkeypatch.setenv("VOLCENGINE_TOS_AK", "TOSAK_smoke123")
    monkeypatch.setenv("VOLCENGINE_TOS_SK", "TOSSK_smoke123")
    monkeypatch.setenv("VOLCENGINE_TOS_BUCKET", "manhuaju-test")
    from manhuaju.core.provider_settings import get_provider_settings

    s = get_provider_settings(refresh=True)
    assert s.has_anthropic is True
    assert s.has_xiaoyunque is True
    assert s.has_tos is True
    summary = s.summary()
    # Keys are masked
    assert "smoke" not in json.dumps(summary)
    assert summary["anthropic"]["enabled"] is True
    assert summary["volcengine_visual"]["ak"].endswith("3456")


def test_v4_acceptance_all_pass():
    from manhuaju.services.kpi import v4_acceptance

    manifest = {"episodes": [{"id": "ep01"}]}
    result = v4_acceptance(
        manifest=manifest,
        seven_dim_mean=8.4,
        seven_dim_worst=7.2,
        cross_episode_arcface_min=0.94,
        garbled_text_rate=0.0,
        sensitive_high_hit_count=0,
        platforms_exported=["douyin", "kuaishou", "weixin"],
        cover_present=True,
        copy_present=True,
        cost_rmb_per_ep=58.0,
        runtime_s_per_ep=1500.0,
    )
    assert result["all_pass"] is True
    assert result["n_pass"] == 8


def test_v4_acceptance_blocks_on_face_drift():
    from manhuaju.services.kpi import v4_acceptance

    result = v4_acceptance(
        manifest={"episodes": []},
        seven_dim_mean=8.4,
        seven_dim_worst=7.2,
        cross_episode_arcface_min=0.85,
        garbled_text_rate=0.0,
        sensitive_high_hit_count=0,
        platforms_exported=["douyin", "kuaishou", "weixin"],
        cover_present=True,
        copy_present=True,
        cost_rmb_per_ep=58.0,
        runtime_s_per_ep=1500.0,
    )
    assert result["all_pass"] is False
    # gate 1 fails
    gate1 = next(it for it in result["items"] if it["name"] == "REQ-V4-001")
    assert gate1["pass"] is False


def test_content_safety_guard_blocks_high(tmp_path):
    yaml_path = tmp_path / "sw.yaml"
    yaml_path.write_text(
        "version: 1\nlevels:\n  high:\n    categories:\n      x:\n        - 暴动\n  medium:\n    categories: {}\n  low:\n    categories: {}\n",
        encoding="utf-8",
    )
    from manhuaju.services.content_safety import ContentSafetyGuard

    g = ContentSafetyGuard(sensitive_words_path=yaml_path)
    v = g.guard("此处发生暴动事件")
    assert v.verdict == "block"
    assert any(h.level == "high" for h in v.hits)


def test_copyright_simhash_self_similarity():
    from manhuaju.services.copyright_check import hamming, simhash

    a = simhash("一日春风遍江南，桃花落尽，山色如黛。")
    b = simhash("一日春风遍江南，桃花落尽，山色如黛！")
    assert hamming(a, b) <= 12  # nearly identical


def test_subtitle_ass_native_writer(tmp_path):
    from manhuaju.services.subtitle_ass import SubtitleLine, render_ass

    lines = [
        SubtitleLine(start_s=0.0, end_s=2.0, text="第一句", speaker="A"),
        SubtitleLine(start_s=2.0, end_s=4.5, text="第二句\n带换行", speaker="B"),
        SubtitleLine(start_s=4.5, end_s=7.0, text="旁白", line_type="narration"),
    ]
    out = tmp_path / "sub.ass"
    res = render_ass(lines, out_path=out, genre="ancient")
    assert res.n_lines == 3
    body = Path(res.ass_path).read_text(encoding="utf-8")
    assert "[V4+ Styles]" in body
    assert "第一句" in body
    assert "第二句\\N带换行" in body


def test_iteration_manager_v4_routes():
    from manhuaju.agents.iteration_manager_agent import IterationManagerAgent
    from manhuaju.core.agent_base import (
        AgentContext,
        AgentRunRequest,
        BudgetSpec,
        TraceContext,
    )
    from manhuaju.core.budget_service import BudgetService, make_budget
    from manhuaju.core.event_bus import InMemoryEventBus
    from manhuaju.core.provenance import ProvenanceStore
    from manhuaju.core.storage import LocalFSStorage
    from pathlib import Path as P

    base = P("./.test_iteration_v4")
    base.mkdir(parents=True, exist_ok=True)
    ctx = AgentContext(
        storage=LocalFSStorage(base),
        bus=InMemoryEventBus(base / "events.jsonl"),
        budget=BudgetService(make_budget("S")),
        provenance=ProvenanceStore(base / "provenance"),
        config={},
    )
    agent = IterationManagerAgent(ctx)
    req = AgentRunRequest(
        inputs={
            "shot_reports": [],
            "drifted": [],
            "vlm_reports": [
                {
                    "shot_id": "sh001",
                    "verdict": "repair",
                    "issues": [
                        {"type": "face_drift", "frame": 2, "severity": "high"},
                        {"type": "text_garbled", "frame": 0, "severity": "high"},
                    ],
                    "scores": {"structure": 7, "no_distortion": 5},
                },
            ],
        },
        context=TraceContext(project_id="test"),
        budgets=BudgetSpec(),
    )
    resp = agent.run(req)
    plans = resp.outputs["plans"]
    assert len(plans) >= 2
    kinds = {p["adapter_kind"] for p in plans}
    assert "wanflf" in kinds
    assert "overlay" in kinds


def test_face_consistency_mock_backend():
    from manhuaju.services.face_consistency import FaceConsistencyService

    svc = FaceConsistencyService()
    assert svc.backend in ("insightface", "mock")
    # cosine smoke
    v1, _ = svc._mock_embed(b"hello")
    v2, _ = svc._mock_embed(b"hello")
    sim = svc.cosine(v1, v2)
    assert 0.99 <= sim <= 1.01


def test_asset_store_roundtrip(tmp_path):
    from manhuaju.core.asset_store import (
        CharacterAssetRecord,
        CharacterAssetStore,
        SceneAssetCache,
        VersionStore,
    )

    cstore = CharacterAssetStore(tmp_path / "c.db")
    rec = CharacterAssetRecord(
        char_id="hero",
        outfit_id="default",
        project_id="proj1",
        local_paths=["/tmp/a.png"],
        public_urls=["https://x/a.png"],
        provider="seedream",
    )
    cstore.put(rec)
    got = cstore.get("proj1", "hero", "default")
    assert got is not None
    assert got.public_urls == ["https://x/a.png"]

    sstore = SceneAssetCache(tmp_path / "s.db")
    sstore.store("ancient|loc1|day|clear", {"local_paths": ["a"], "public_urls": ["b"]})
    assert sstore.lookup("ancient|loc1|day|clear") is not None

    vstore = VersionStore(tmp_path / "v.db")
    vstore.record(
        version_id="v1",
        project_id="proj1",
        artefact_kind="cover",
        artefact_uri="/tmp/c.jpg",
        params={"seed": 42},
        eval_scores={"score": 8.5},
    )
    assert len(vstore.list_by_project("proj1")) == 1


@pytest.mark.parametrize(
    "issue_type,expected_kind",
    [
        ("face_drift", "wanflf"),
        ("text_garbled", "overlay"),
        ("axis_violation", "seedance"),
        ("style_offshift", "xiaoyunque"),
        ("intent_mismatch", "xiaoyunque"),
    ],
)
def test_repair_routes(issue_type, expected_kind):
    from manhuaju.core.failure_modes import repair_route_for

    kind, _ = repair_route_for(issue_type)
    assert kind == expected_kind
