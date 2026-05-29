"""Episode pipeline — 6-step workflow with draw/rough/fine cut."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from manhuaju.adapters.llm.mock_llm_adapter import MockLLMAdapter
from manhuaju.adapters.music.mock_music_adapter import MockMusicAdapter
from manhuaju.adapters.qa.mock_qa_evaluator_adapter import MockQAEvaluatorAdapter
from manhuaju.adapters.render.mock_seedance_adapter import MockSeedanceAdapter
from manhuaju.adapters.render.mock_xiaoyunque_adapter import MockXiaoyunqueAdapter
from manhuaju.adapters.tts.mock_tts_adapter import MockTTSAdapter
from manhuaju.agents.dialogue_optimizer_agent import DialogueOptimizerAgent
from manhuaju.agents.iteration_manager_agent import IterationManagerAgent
from manhuaju.agents.music_director_agent import MusicDirectorAgent
from manhuaju.agents.qa_reviewer_agent import QAReviewerAgent
from manhuaju.agents.render_orchestrator_agent import RenderOrchestratorAgent
from manhuaju.agents.script_writer_agent import ScriptWriterAgent
from manhuaju.agents.storyboard_director_agent import StoryboardDirectorAgent
from manhuaju.agents.voice_director_agent import VoiceDirectorAgent
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, TraceContext
from manhuaju.core.review_gate import ReviewGate
from manhuaju.core.seed import episode_seed
from manhuaju.core.state_machine import EpisodeState
from manhuaju.core.workflow_config import load_workflow_config
from manhuaju.core.workflow_stage import WorkflowStage, emit_workflow_stage
from manhuaju.pipelines.fine_cut import fine_cut_episode
from manhuaju.pipelines.rough_cut import rough_cut_episode
from manhuaju.services.seven_dim_qa import score_episode


class EpisodePipeline:
    def __init__(
        self,
        ctx: AgentContext,
        *,
        llm: MockLLMAdapter,
        tts: MockTTSAdapter,
        music: MockMusicAdapter,
        xy: MockXiaoyunqueAdapter,
        seedance: MockSeedanceAdapter,
        qa: MockQAEvaluatorAdapter,
        max_repairs: int = 3,
        resolution: str = "720p",
        fps: int = 12,
        mock_shot_duration_s: int = 1,
        max_shots_per_episode: int = 8,
        max_dialogue_lines: int = 2,
        reference_map: dict[str, list[str]] | None = None,
        review_gate: ReviewGate | None = None,
    ) -> None:
        self.ctx = ctx
        self.llm = llm
        self.tts = tts
        self.music = music
        self.xy = xy
        self.seedance = seedance
        self.qa = qa
        self.max_repairs = max_repairs
        self.resolution = resolution
        self.fps = fps
        self.mock_shot_duration_s = mock_shot_duration_s
        self.max_shots_per_episode = max_shots_per_episode
        self.max_dialogue_lines = max_dialogue_lines
        self.reference_map = reference_map or {}
        self.review_gate = review_gate or ReviewGate(mode="autopilot")
        self.workflow = load_workflow_config(ctx.config)

    def run(
        self,
        *,
        project_id: str,
        project_seed_value: int,
        episode: dict[str, Any],
        characters: list[dict[str, Any]],
        bibles: list[dict[str, Any]],
        style: dict[str, Any],
        out_dir: Path,
    ) -> dict[str, Any]:
        ep_id = episode["episode_id"]
        seed = episode_seed(project_seed_value, ep_id)
        trace = TraceContext(project_id=project_id, episode_id=ep_id)
        self._emit_state(project_id, ep_id, EpisodeState.DRAFTED)
        emit_workflow_stage(
            self.ctx.bus,
            project_id=project_id,
            episode_id=ep_id,
            stage=WorkflowStage.PROMPTS,
        )

        sw = ScriptWriterAgent(self.ctx, llm=self.llm)
        script = sw.run(
            AgentRunRequest(
                inputs={"episode": episode, "characters": characters},
                context=trace,
                seed=seed,
            )
        ).outputs["script"]

        do = DialogueOptimizerAgent(self.ctx, llm=self.llm)
        script = do.run(
            AgentRunRequest(inputs={"script": script}, context=trace, seed=seed)
        ).outputs["script"]
        self._emit_state(project_id, ep_id, EpisodeState.STORYBOARDED)

        sd = StoryboardDirectorAgent(self.ctx, llm=self.llm)
        storyboard = sd.run(
            AgentRunRequest(
                inputs={"script": script, "style_sha": style["style_sha"]},
                context=trace,
                seed=seed,
            )
        ).outputs["storyboard"]
        if len(storyboard["shots"]) > self.max_shots_per_episode:
            storyboard = {
                **storyboard,
                "shots": storyboard["shots"][: self.max_shots_per_episode],
            }
        rendered_shots = []
        for sh in storyboard["shots"]:
            new_sh = dict(sh)
            new_sh["target_seconds_intent"] = sh["target_seconds"]
            new_sh["target_seconds"] = self.mock_shot_duration_s
            rendered_shots.append(new_sh)
        storyboard = {**storyboard, "shots": rendered_shots}

        retry_counts: dict[str, int] = {}
        cycles = 0
        last_qa = None
        last_renders = None
        last_tts = None
        last_qa7 = None
        while cycles <= self.max_repairs:
            emit_workflow_stage(
                self.ctx.bus,
                project_id=project_id,
                episode_id=ep_id,
                stage=WorkflowStage.DRAW,
            )
            self._emit_state(project_id, ep_id, EpisodeState.RENDERING)
            ro = RenderOrchestratorAgent(self.ctx, xy=self.xy, seedance=self.seedance)
            ro_resp = ro.run(
                AgentRunRequest(
                    inputs={
                        "storyboard": storyboard,
                        "style_sha": style["style_sha"],
                        "visual_style": style.get("visual_style", ""),
                        "episode_seed": seed,
                        "resolution": self.resolution,
                        "fps": self.fps,
                        "retry_counts": retry_counts,
                        "candidates_per_shot": self.workflow.candidates_per_shot,
                        "reference_map": self.reference_map,
                    },
                    context=trace,
                    seed=seed,
                )
            )
            renders = ro_resp.outputs["shots"]
            last_renders = renders

            self._emit_state(project_id, ep_id, EpisodeState.AUDIO_MIXING)
            vd = VoiceDirectorAgent(self.ctx, tts=self.tts)
            small_script = {**script, "dialogues": script["dialogues"][: self.max_dialogue_lines]}
            vd_resp = vd.run(
                AgentRunRequest(
                    inputs={"bibles": bibles, "script": small_script},
                    context=trace,
                    seed=seed,
                )
            )
            tts_lines = vd_resp.outputs["lines"]
            last_tts = tts_lines

            md = MusicDirectorAgent(self.ctx, music=self.music)
            md_resp = md.run(
                AgentRunRequest(
                    inputs={
                        "episode_id": ep_id,
                        "target_seconds": max(
                            2.0, sum(s["target_seconds"] for s in storyboard["shots"]) / 4
                        ),
                        "mood": "tense",
                    },
                    context=trace,
                    seed=seed,
                )
            )
            bgm_uri = md_resp.outputs["bgm"]["bgm_uri"]

            self._emit_state(project_id, ep_id, EpisodeState.IN_QA)
            qaa = QAReviewerAgent(self.ctx, qa=self.qa)
            qa_resp = qaa.run(
                AgentRunRequest(
                    inputs={
                        "storyboard": storyboard,
                        "renders": renders,
                        "tts_lines": tts_lines,
                    },
                    context=trace,
                    seed=seed,
                )
            )
            last_qa = qa_resp.outputs
            last_qa7 = score_episode(
                storyboard=storyboard,
                renders=renders,
                style_sha=style["style_sha"],
            )
            last_qa["seven_dim_qa"] = last_qa7

            ep_report = qa_resp.outputs["episode_report"]
            if ep_report["promoted"]:
                self._emit_state(project_id, ep_id, EpisodeState.PROMOTED)
                break
            cycles += 1
            if cycles > self.max_repairs:
                self._emit_state(project_id, ep_id, EpisodeState.QUARANTINED)
                break
            self._emit_state(project_id, ep_id, EpisodeState.REPAIRING)
            it = IterationManagerAgent(self.ctx)
            it_resp = it.run(
                AgentRunRequest(
                    inputs={
                        "shot_reports": qa_resp.outputs["shot_reports"],
                        "drifted": [],
                    },
                    context=trace,
                    seed=seed,
                )
            )
            cycle_uri = self.ctx.storage.write_json(
                f"{project_id}/10_iterations/{ep_id}_cycle_{cycles:02d}.json",
                {
                    "cycle": cycles,
                    "episode_id": ep_id,
                    "plans": it_resp.outputs["plans"],
                    "before_pass_rate": ep_report["pass_rate"],
                    "before_arcface_mean": ep_report["arcface_mean"],
                    "before_aesthetic_mean": ep_report["aesthetic_mean"],
                    "seven_dim_qa": last_qa7,
                },
            )
            self.ctx.bus.publish(
                "manhuaju.event.iteration.cycle",
                project_id=project_id,
                episode_id=ep_id,
                payload={"cycle": cycles, "uri": str(cycle_uri)},
            )
            for plan in it_resp.outputs["plans"]:
                if plan["target"] == "shot":
                    retry_counts[plan["target_id"]] = retry_counts.get(plan["target_id"], 0) + 1
            if not any(p["target"] in ("shot", "char_refs") for p in it_resp.outputs["plans"]):
                break

        if last_renders is None:
            raise RuntimeError("No renders produced; pipeline aborted unexpectedly.")
        shot_paths = [Path(r["output_uri"]) for r in last_renders if r["output_uri"]]
        ep_out_dir = out_dir / "episodes"
        bgm_path = Path(bgm_uri) if bgm_uri else None

        emit_workflow_stage(
            self.ctx.bus,
            project_id=project_id,
            episode_id=ep_id,
            stage=WorkflowStage.ROUGH_CUT,
        )
        rough = rough_cut_episode(
            shot_mp4s=shot_paths,
            bgm_wav=bgm_path,
            out_dir=ep_out_dir,
            episode_id=ep_id,
        )

        emit_workflow_stage(
            self.ctx.bus,
            project_id=project_id,
            episode_id=ep_id,
            stage=WorkflowStage.FINE_CUT,
        )
        captions = [d.get("text", "") for d in script.get("dialogues", [])]
        final_mp4 = fine_cut_episode(
            rough_mp4=rough,
            bgm_wav=bgm_path,
            out_dir=ep_out_dir,
            episode_id=ep_id,
            captions=captions,
            fallback_caption=episode["title"],
        )

        awaiting_review = False
        if self.review_gate.should_wait() and last_qa and last_qa["episode_report"]["promoted"]:
            awaiting_review = not self.review_gate.is_release_allowed(project_id, ep_id)
            if awaiting_review:
                self.ctx.bus.publish(
                    "manhuaju.event.review.awaiting",
                    project_id=project_id,
                    episode_id=ep_id,
                    payload={"state": "AwaitingReview"},
                )

        return {
            "episode_id": ep_id,
            "final_mp4": str(final_mp4),
            "rough_mp4": str(rough),
            "qa": last_qa,
            "seven_dim_qa": last_qa7,
            "renders": last_renders,
            "tts_lines": last_tts,
            "cycles": cycles,
            "promoted": (last_qa["episode_report"]["promoted"] if last_qa else False),
            "awaiting_review": awaiting_review,
            "shot_signatures": {
                s["char_id"]: s["outfit_id"]
                for shot in storyboard["shots"]
                for s in shot["characters"]
            },
            "storyboard": storyboard,
        }

    def _emit_state(self, project_id: str, ep_id: str, state: EpisodeState) -> None:
        self.ctx.bus.publish(
            "manhuaju.event.episode.state",
            project_id=project_id,
            episode_id=ep_id,
            payload={"state": state.value},
        )
