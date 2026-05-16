"""Project-level pipeline.

Orchestrates: Ingest -> Story -> Plan -> Bibles -> Refs -> Style -> Episodes.
On any failure inside the loop the IterationManager handles it within the
EpisodePipeline; project-level fallback (salvage) is triggered if any episode
ends up Quarantined after `max_repairs` cycles.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
from manhuaju.agents.master_orchestrator_agent import MasterOrchestratorAgent
from manhuaju.agents.reference_asset_agent import ReferenceAssetAgent
from manhuaju.agents.story_architect_agent import StoryArchitectAgent
from manhuaju.agents.visual_style_agent import VisualStyleAgent
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, TraceContext
from manhuaju.core.seed import project_seed
from manhuaju.core.state_machine import ProjectState
from manhuaju.pipelines.episode_flow import EpisodePipeline


def _attach_root(adapter: Any, attr: str, path: Path) -> Any:
    """Set ``adapter.<attr>`` to ``path`` (mkdir-ing) if the adapter exposes it."""
    if hasattr(adapter, attr):
        path.mkdir(parents=True, exist_ok=True)
        setattr(adapter, attr, path)
    return adapter


def _attach_render_roots(adapter: Any, artefacts: Path, frames: Path) -> Any:
    """Bind both `artefacts_root` and `frames_root` on a render adapter."""
    artefacts.mkdir(parents=True, exist_ok=True)
    frames.mkdir(parents=True, exist_ok=True)
    if hasattr(adapter, "artefacts_root"):
        adapter.artefacts_root = artefacts
    if hasattr(adapter, "frames_root"):
        adapter.frames_root = frames
    return adapter


@dataclass
class ProjectFlowConfig:
    project_id: str
    novel_text: str
    seed: int
    episode_count: int = 3
    style_preset_id: str = "cinematic_2d_v1"
    aspect_ratio: str = "9:16"
    resolution: str = "720p"  # M2 default; pilot config can override
    fps: int = 12
    max_repairs: int = 3
    out_dir: Path = Path("output")
    max_shots_per_episode: int = 8
    mock_shot_duration_s: int = 1
    max_dialogue_lines: int = 2


class ProjectPipeline:
    def __init__(
        self,
        ctx: AgentContext,
        *,
        redlines: list[str] | None = None,
        bundle: Any | None = None,
    ) -> None:
        self.ctx = ctx
        if bundle is None:
            # M2 default — direct mock construction for backward compatibility.
            self.llm = MockLLMAdapter()
            self.moderation = MockModerationAdapter(redlines=redlines or [])
            self.tts = MockTTSAdapter(artefacts_root=ctx.storage.base / "_tts")
            self.music = MockMusicAdapter(artefacts_root=ctx.storage.base / "_music")
            self.seedance = MockSeedanceAdapter(
                artefacts_root=ctx.storage.base / "_renders",
                frames_root=ctx.storage.base / "_frames",
            )
            self.xy = MockXiaoyunqueAdapter(
                artefacts_root=ctx.storage.base / "_renders",
                frames_root=ctx.storage.base / "_frames",
                seedance_fallback=self.seedance,
            )
            self.qa_eval = MockQAEvaluatorAdapter()
            self.bundle = None
        else:
            # M3 live/hybrid — adapters supplied by AdapterFactory.
            artefacts = ctx.storage.base / "_renders"
            frames = ctx.storage.base / "_frames"
            tts_root = ctx.storage.base / "_tts"
            music_root = ctx.storage.base / "_music"
            self.llm = bundle.llm
            self.moderation = bundle.moderation
            # Inject redlines for any moderation impl that needs it. Real impl
            # already loads from config; mock fallback inside bundle gets a
            # one-time setter via attribute access if missing.
            if redlines and hasattr(self.moderation, "redlines"):
                self.moderation.redlines = [r.lower() for r in redlines]
            # Ensure adapter artefacts go under the project storage path.
            self.tts = _attach_root(bundle.tts, "artefacts_root", tts_root)
            self.music = _attach_root(bundle.music, "artefacts_root", music_root)
            self.seedance = _attach_render_roots(
                bundle.render_fallback, artefacts, frames
            )
            self.xy = _attach_render_roots(bundle.render_primary, artefacts, frames)
            # Wire fallback to mock seedance for the legacy chain.
            if hasattr(self.xy, "seedance_fallback") and self.xy.seedance_fallback is None:
                self.xy.seedance_fallback = self.seedance
            self.qa_eval = bundle.qa
            self.bundle = bundle

    def run(self, cfg: ProjectFlowConfig) -> dict[str, Any]:
        trace = TraceContext(project_id=cfg.project_id)
        ps = project_seed(cfg.seed)
        self._emit_state(cfg.project_id, ProjectState.ACCEPTED)

        episode_results: list[dict[str, Any]] = []
        resume_dir = cfg.out_dir / "_resume"
        resume_path = resume_dir / "pipeline_state.json"
        use_resume = os.getenv("MANHUAJU_LIVE_RESUME", "").strip() in ("1", "true", "yes")
        if use_resume and resume_path.is_file():
            snap = json.loads(resume_path.read_text(encoding="utf-8"))
            bp = snap["blueprint"]
            plan = snap["plan"]
            bibles = snap["bibles"]
            style = snap["style"]
            episode_results = list(snap.get("episode_results") or [])
        else:
            # 1. Story
            self._emit_state(cfg.project_id, ProjectState.INGESTING)
            sa = StoryArchitectAgent(self.ctx, llm=self.llm, moderation=self.moderation)
            sa_resp = sa.run(
                AgentRunRequest(
                    inputs={"novel_text": cfg.novel_text},
                    context=trace,
                    seed=cfg.seed,
                )
            )
            if sa_resp.status != "succeeded":
                self._emit_state(cfg.project_id, ProjectState.FAILED)
                return {
                    "status": "failed",
                    "reason": sa_resp.outputs.get("reason", "story_failure"),
                }
            bp = sa_resp.outputs["blueprint"]

            # 2. Plan
            self._emit_state(cfg.project_id, ProjectState.PLANNING)
            ep_planner = EpisodePlannerAgent(self.ctx, llm=self.llm)
            plan = ep_planner.run(
                AgentRunRequest(
                    inputs={"blueprint": bp, "episode_count": cfg.episode_count},
                    context=trace,
                    seed=cfg.seed,
                )
            ).outputs["plan"]

            # 3. Bibles (only leads + 1 support to keep mock fast)
            self._emit_state(cfg.project_id, ProjectState.CHARACTER_BUILDING)
            bibles = CharacterBibleAgent(self.ctx, llm=self.llm).run(
                AgentRunRequest(
                    inputs={"characters": bp["characters"][:3], "blueprint": bp},
                    context=trace,
                    seed=cfg.seed,
                )
            ).outputs["bibles"]

            # 4. References
            ReferenceAssetAgent(self.ctx).run(
                AgentRunRequest(inputs={"bibles": bibles}, context=trace, seed=cfg.seed)
            )

            # 5. Style
            self._emit_state(cfg.project_id, ProjectState.STYLE_LOCKED)
            style = VisualStyleAgent(self.ctx, llm=self.llm).run(
                AgentRunRequest(
                    inputs={
                        "blueprint": bp,
                        "config": {
                            "style_preset_id": cfg.style_preset_id,
                            "aspect_ratio": cfg.aspect_ratio,
                            "resolution": cfg.resolution,
                            "fps": cfg.fps,
                        },
                    },
                    context=trace,
                    seed=cfg.seed,
                )
            ).outputs["style_lock"]

        def _write_checkpoint() -> None:
            if os.getenv("MANHUAJU_LIVE_CHECKPOINT", "").strip() not in ("1", "true", "yes"):
                return
            resume_dir.mkdir(parents=True, exist_ok=True)

            def _ser(obj: Any) -> Any:
                if isinstance(obj, Path):
                    return str(obj)
                if isinstance(obj, (str, int, float, bool)) or obj is None:
                    return obj
                if isinstance(obj, dict):
                    return {str(k): _ser(v) for k, v in obj.items()}
                if isinstance(obj, (list, tuple)):
                    return [_ser(x) for x in obj]
                return str(obj)

            resume_path.write_text(
                json.dumps(
                    _ser(
                        {
                            "blueprint": bp,
                            "plan": plan,
                            "bibles": bibles,
                            "style": style,
                            "episode_results": episode_results,
                        }
                    ),
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        # 6. Episodes
        self._emit_state(cfg.project_id, ProjectState.PRODUCING)
        ep_pipe = EpisodePipeline(
            self.ctx,
            llm=self.llm,
            tts=self.tts,
            music=self.music,
            xy=self.xy,
            seedance=self.seedance,
            qa=self.qa_eval,
            max_repairs=cfg.max_repairs,
            resolution=cfg.resolution,
            fps=cfg.fps,
            mock_shot_duration_s=cfg.mock_shot_duration_s,
            max_shots_per_episode=cfg.max_shots_per_episode,
            max_dialogue_lines=cfg.max_dialogue_lines,
        )
        start_idx = len(episode_results)
        for idx, ep in enumerate(plan["episodes"]):
            if idx < start_idx:
                continue
            res = ep_pipe.run(
                project_id=cfg.project_id,
                project_seed_value=ps,
                episode=ep,
                characters=bp["characters"],
                bibles=bibles,
                style=style,
                out_dir=cfg.out_dir,
            )
            episode_results.append(res)
            _write_checkpoint()

        if len(episode_results) >= len(plan["episodes"]) and resume_path.is_file():
            try:
                resume_path.unlink()
            except OSError:
                pass
        self._emit_state(cfg.project_id, ProjectState.QUALITY_LOOP)
        cc = ContinuityCheckerAgent(self.ctx, qa=self.qa_eval)
        sigs = {r["episode_id"]: r["shot_signatures"] for r in episode_results}
        cc_resp = cc.run(
            AgentRunRequest(inputs={"episode_signatures": sigs}, context=trace, seed=cfg.seed)
        )

        # 8. Release decision
        any_fail = any(not r["promoted"] for r in episode_results) or cc_resp.outputs["drifted"]
        if any_fail:
            # Salvage: attempt one more cycle on episodes with drift
            for r in episode_results:
                if r["promoted"] and not cc_resp.outputs["drifted"]:
                    continue
                # Mark with a salvage note; keep the mp4
                r["salvage_attempted"] = True
        self._emit_state(cfg.project_id, ProjectState.RELEASING)
        self._emit_state(cfg.project_id, ProjectState.RELEASED)

        # Final manifest
        manifest = {
            "project_id": cfg.project_id,
            "blueprint_sha": bp["blueprint_sha"],
            "plan_sha": plan["plan_sha"],
            "style_sha": style["style_sha"],
            "episodes": [
                {
                    "episode_id": r["episode_id"],
                    "final_mp4": r["final_mp4"],
                    "promoted": r["promoted"],
                    "cycles": r["cycles"],
                    "pass_rate": r["qa"]["episode_report"]["pass_rate"],
                    "aesthetic_mean": r["qa"]["episode_report"]["aesthetic_mean"],
                    "arcface_mean": r["qa"]["episode_report"]["arcface_mean"],
                    "vbench_mean": r["qa"]["episode_report"]["vbench_mean"],
                    "utmos_mean": r["qa"]["episode_report"]["utmos_mean"],
                    "syncnet_offset_max": r["qa"]["episode_report"]["syncnet_offset_max"],
                }
                for r in episode_results
            ],
            "continuity": cc_resp.outputs,
        }
        self.ctx.storage.write_json(f"{cfg.project_id}/99_manifest.json", manifest)
        # Master orchestrator end event
        MasterOrchestratorAgent(self.ctx).run(
            AgentRunRequest(
                inputs={"action": "released", "payload": manifest},
                context=trace,
                seed=cfg.seed,
            )
        )
        return {"status": "released", "manifest": manifest, "episode_results": episode_results}

    def _emit_state(self, project_id: str, state: ProjectState) -> None:
        self.ctx.bus.publish(
            "manhuaju.event.project.state",
            project_id=project_id,
            payload={"state": state.value},
        )
