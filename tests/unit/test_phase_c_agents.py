"""Phase C smoke gate: 14 Agents wired through real Mock Adapters."""

from __future__ import annotations

from pathlib import Path

import pytest

from manhuaju.adapters.llm.mock_llm_adapter import MockLLMAdapter
from manhuaju.adapters.moderation.mock_moderation_adapter import MockModerationAdapter
from manhuaju.adapters.music.mock_music_adapter import MockMusicAdapter
from manhuaju.adapters.qa.mock_qa_evaluator_adapter import MockQAEvaluatorAdapter
from manhuaju.adapters.render.mock_seedance_adapter import MockSeedanceAdapter
from manhuaju.adapters.render.mock_xiaoyunque_adapter import MockXiaoyunqueAdapter
from manhuaju.adapters.tts.mock_tts_adapter import MockTTSAdapter
from manhuaju.agents.character_bible_agent import CharacterBibleAgent
from manhuaju.agents.continuity_checker_agent import ContinuityCheckerAgent
from manhuaju.agents.episode_planner_agent import EpisodePlannerAgent
from manhuaju.agents.iteration_manager_agent import IterationManagerAgent
from manhuaju.agents.master_orchestrator_agent import MasterOrchestratorAgent
from manhuaju.agents.music_director_agent import MusicDirectorAgent
from manhuaju.agents.qa_reviewer_agent import QAReviewerAgent
from manhuaju.agents.reference_asset_agent import ReferenceAssetAgent
from manhuaju.agents.render_orchestrator_agent import RenderOrchestratorAgent
from manhuaju.agents.script_writer_agent import ScriptWriterAgent
from manhuaju.agents.story_architect_agent import StoryArchitectAgent
from manhuaju.agents.storyboard_director_agent import StoryboardDirectorAgent
from manhuaju.agents.visual_style_agent import VisualStyleAgent
from manhuaju.agents.voice_director_agent import VoiceDirectorAgent
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, TraceContext
from manhuaju.core.budget_service import BudgetService, make_budget
from manhuaju.core.event_bus import InMemoryEventBus
from manhuaju.core.provenance import ProvenanceStore
from manhuaju.core.storage import LocalFSStorage


@pytest.fixture
def ctx(tmp_path: Path) -> AgentContext:
    return AgentContext(
        storage=LocalFSStorage(tmp_path / "fs"),
        bus=InMemoryEventBus(tmp_path / "events.jsonl"),
        budget=BudgetService(make_budget("S")),
        provenance=ProvenanceStore(tmp_path / "prov"),
        config={},
    )


def _trace(project_id: str = "proj_1", episode_id: str | None = None) -> TraceContext:
    return TraceContext(project_id=project_id, episode_id=episode_id)


def test_full_agent_chain_minimal(ctx: AgentContext, tmp_path: Path) -> None:
    llm = MockLLMAdapter()
    mod = MockModerationAdapter(redlines=["xxxnonexistent"])
    qa = MockQAEvaluatorAdapter()
    tts = MockTTSAdapter(artefacts_root=tmp_path / "tts")
    music = MockMusicAdapter(artefacts_root=tmp_path / "music")
    seedance = MockSeedanceAdapter(artefacts_root=tmp_path / "ren", frames_root=tmp_path / "fr")
    xy = MockXiaoyunqueAdapter(
        artefacts_root=tmp_path / "ren", frames_root=tmp_path / "fr", seedance_fallback=seedance
    )

    # 1. Story
    sa = StoryArchitectAgent(ctx, llm=llm, moderation=mod)
    sa_resp = sa.run_with_telemetry(
        AgentRunRequest(
            inputs={"novel_text": "林云雀和陈翊在天港相遇。" * 60},
            context=_trace(),
            seed=1,
        )
    )
    assert sa_resp.status == "succeeded"
    bp = sa_resp.outputs["blueprint"]

    # 2. Plan
    ep = EpisodePlannerAgent(ctx, llm=llm)
    ep_resp = ep.run(
        AgentRunRequest(
            inputs={"blueprint": bp, "episode_count": 3},
            context=_trace(),
            seed=1,
        )
    )
    plan = ep_resp.outputs["plan"]
    assert len(plan["episodes"]) == 3

    # 3. Bible
    cb = CharacterBibleAgent(ctx, llm=llm)
    cb_resp = cb.run(
        AgentRunRequest(
            inputs={"characters": bp["characters"][:2], "blueprint": bp},
            context=_trace(),
            seed=1,
        )
    )
    bibles = cb_resp.outputs["bibles"]
    assert len(bibles) == 2

    # 4. References (real PNGs)
    ra = ReferenceAssetAgent(ctx)
    ra_resp = ra.run(AgentRunRequest(inputs={"bibles": bibles}, context=_trace(), seed=1))
    assert ra_resp.outputs["references"]

    # 5. Style
    vs = VisualStyleAgent(ctx, llm=llm)
    vs_resp = vs.run(
        AgentRunRequest(
            inputs={"blueprint": bp, "config": {"style_preset_id": "cinematic_2d_v1"}},
            context=_trace(),
            seed=1,
        )
    )
    style = vs_resp.outputs["style_lock"]

    # 6. Script for first episode
    sw = ScriptWriterAgent(ctx, llm=llm)
    sw_resp = sw.run(
        AgentRunRequest(
            inputs={"episode": plan["episodes"][0], "characters": bp["characters"]},
            context=_trace(episode_id="ep01"),
            seed=1,
        )
    )
    script = sw_resp.outputs["script"]

    # 7. Storyboard
    sd = StoryboardDirectorAgent(ctx, llm=llm)
    sd_resp = sd.run(
        AgentRunRequest(
            inputs={"script": script, "style_sha": style["style_sha"]},
            context=_trace(episode_id="ep01"),
            seed=1,
        )
    )
    sb = sd_resp.outputs["storyboard"]
    # Limit shots for a fast test
    sb_small = {**sb, "shots": sb["shots"][:2]}

    # 8. Voice (TTS)
    vd = VoiceDirectorAgent(ctx, tts=tts)
    # take only first 2 lines to keep test fast
    script_small = {**script, "dialogues": script["dialogues"][:2]}
    vd_resp = vd.run(
        AgentRunRequest(
            inputs={"bibles": bibles, "script": script_small},
            context=_trace(episode_id="ep01"),
            seed=1,
        )
    )
    assert vd_resp.outputs["lines"]

    # 9. Music
    md = MusicDirectorAgent(ctx, music=music)
    md_resp = md.run(
        AgentRunRequest(
            inputs={"episode_id": "ep01", "target_seconds": 1.0, "mood": "tense"},
            context=_trace(episode_id="ep01"),
            seed=1,
        )
    )
    assert Path(md_resp.outputs["bgm"]["bgm_uri"]).exists()

    # 10. Render
    ro = RenderOrchestratorAgent(ctx, xy=xy, seedance=seedance)
    # shorten target_seconds in storyboard to keep test fast
    for sh in sb_small["shots"]:
        sh["target_seconds"] = 1
    ro_resp = ro.run(
        AgentRunRequest(
            inputs={
                "storyboard": sb_small,
                "style_sha": style["style_sha"],
                "episode_seed": 12345,
                "resolution": "720p",
                "fps": 12,
                "retry_counts": {},
            },
            context=_trace(episode_id="ep01"),
            seed=1,
        )
    )
    assert all(r["output_uri"] for r in ro_resp.outputs["shots"])

    # 11. QA
    qaa = QAReviewerAgent(ctx, qa=qa)
    qa_resp = qaa.run(
        AgentRunRequest(
            inputs={
                "storyboard": sb_small,
                "renders": ro_resp.outputs["shots"],
                "tts_lines": vd_resp.outputs["lines"],
            },
            context=_trace(episode_id="ep01"),
            seed=1,
        )
    )
    assert qa_resp.outputs["episode_report"]["pass_rate"] >= 0

    # 12. Continuity
    cc = ContinuityCheckerAgent(ctx, qa=qa)
    sigs = {
        "ep01": {bibles[0]["char_id"]: bibles[0]["outfit_library"][0]["outfit_id"]},
        "ep02": {bibles[0]["char_id"]: bibles[0]["outfit_library"][0]["outfit_id"]},
        "ep03": {bibles[0]["char_id"]: bibles[0]["outfit_library"][0]["outfit_id"]},
    }
    cc_resp = cc.run(
        AgentRunRequest(inputs={"episode_signatures": sigs}, context=_trace(), seed=1)
    )
    assert cc_resp.outputs["drifted"] == []

    # 13. IterationManager
    im = IterationManagerAgent(ctx)
    im_resp = im.run(
        AgentRunRequest(
            inputs={
                "shot_reports": qa_resp.outputs["shot_reports"],
                "drifted": [],
            },
            context=_trace(),
            seed=1,
        )
    )
    assert "plans" in im_resp.outputs

    # 14. Master
    mo = MasterOrchestratorAgent(ctx)
    mo_resp = mo.run(
        AgentRunRequest(
            inputs={"action": "released", "payload": {"episode_id": "ep01"}},
            context=_trace(),
            seed=1,
        )
    )
    assert mo_resp.status == "succeeded"
    # Provenance chain still intact
    assert ctx.provenance.verify() is True


def test_iteration_manager_drift_emits_consistency_refresh(ctx: AgentContext) -> None:
    im = IterationManagerAgent(ctx)
    resp = im.run(
        AgentRunRequest(
            inputs={
                "shot_reports": [],
                "drifted": ["char_lead_a"],
            },
            context=_trace(),
            seed=1,
        )
    )
    assert any(p["strategy"] == "consistency_refresh" for p in resp.outputs["plans"])
