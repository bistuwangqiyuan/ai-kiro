"""Episode pipeline (Script -> Storyboard -> Render+Voice+Music -> QA -> Postprod)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from manhuaju.adapters.llm.mock_llm_adapter import MockLLMAdapter
from manhuaju.adapters.music.mock_music_adapter import MockMusicAdapter
from manhuaju.adapters.qa.mock_qa_evaluator_adapter import MockQAEvaluatorAdapter
from manhuaju.adapters.render.mock_seedance_adapter import MockSeedanceAdapter
from manhuaju.adapters.render.mock_xiaoyunque_adapter import MockXiaoyunqueAdapter
from manhuaju.adapters.tts.mock_tts_adapter import MockTTSAdapter
from manhuaju.agents.iteration_manager_agent import IterationManagerAgent
from manhuaju.agents.music_director_agent import MusicDirectorAgent
from manhuaju.agents.qa_reviewer_agent import QAReviewerAgent
from manhuaju.agents.render_orchestrator_agent import RenderOrchestratorAgent
from manhuaju.agents.script_writer_agent import ScriptWriterAgent
from manhuaju.agents.storyboard_director_agent import StoryboardDirectorAgent
from manhuaju.agents.voice_director_agent import VoiceDirectorAgent
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, TraceContext
from manhuaju.core.seed import episode_seed
from manhuaju.core.state_machine import EpisodeState
from manhuaju.pipelines.postprod import episode_postprod


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

        sw = ScriptWriterAgent(self.ctx, llm=self.llm)
        script = sw.run(
            AgentRunRequest(
                inputs={"episode": episode, "characters": characters},
                context=trace,
                seed=seed,
            )
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
        # Limit to a manageable shot count for M2 mock so test runtime stays
        # bounded. Real Seedance/Xiaoyunque integration would not enforce
        # this cap. Also override per-shot duration for mock speed.
        if len(storyboard["shots"]) > self.max_shots_per_episode:
            storyboard = {
                **storyboard,
                "shots": storyboard["shots"][: self.max_shots_per_episode],
            }
        # Force shot duration to mock value (the schema-derived 5/10/15s
        # remains the production-time intent; tracked in `target_seconds_intent`).
        rendered_shots = []
        for sh in storyboard["shots"]:
            new_sh = dict(sh)
            new_sh["target_seconds_intent"] = sh["target_seconds"]
            new_sh["target_seconds"] = self.mock_shot_duration_s
            rendered_shots.append(new_sh)
        storyboard = {**storyboard, "shots": rendered_shots}

        # Render shots (with retry loop)
        retry_counts: dict[str, int] = {}
        accepted_shots: dict[str, Any] = {}
        cycles = 0
        last_qa = None
        last_renders = None
        last_tts = None
        while cycles <= self.max_repairs:
            self._emit_state(project_id, ep_id, EpisodeState.RENDERING)
            ro = RenderOrchestratorAgent(self.ctx, xy=self.xy, seedance=self.seedance)
            ro_resp = ro.run(
                AgentRunRequest(
                    inputs={
                        "storyboard": storyboard,
                        "style_sha": style["style_sha"],
                        "episode_seed": seed,
                        "resolution": self.resolution,
                        "fps": self.fps,
                        "retry_counts": retry_counts,
                    },
                    context=trace,
                    seed=seed,
                )
            )
            renders = ro_resp.outputs["shots"]
            last_renders = renders

            self._emit_state(project_id, ep_id, EpisodeState.AUDIO_MIXING)
            vd = VoiceDirectorAgent(self.ctx, tts=self.tts)
            # Cap dialogue lines to first 2 per episode for M2 speed
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
                        "target_seconds": max(2.0, sum(s["target_seconds"] for s in storyboard["shots"]) / 4),
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

            ep_report = qa_resp.outputs["episode_report"]
            if ep_report["promoted"]:
                accepted_shots = {r["shot_id"]: r for r in renders}  # noqa: F841 (kept for downstream debug)
                _ = accepted_shots
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
            # Persist iteration cycle artefact
            cycle_uri = self.ctx.storage.write_json(
                f"{project_id}/10_iterations/{ep_id}_cycle_{cycles:02d}.json",
                {
                    "cycle": cycles,
                    "episode_id": ep_id,
                    "plans": it_resp.outputs["plans"],
                    "before_pass_rate": ep_report["pass_rate"],
                    "before_arcface_mean": ep_report["arcface_mean"],
                    "before_aesthetic_mean": ep_report["aesthetic_mean"],
                },
            )
            self.ctx.bus.publish(
                "manhuaju.event.iteration.cycle",
                project_id=project_id,
                episode_id=ep_id,
                payload={"cycle": cycles, "uri": str(cycle_uri)},
            )
            # Bump retry counts for shot-targeted plans so seed changes
            for plan in it_resp.outputs["plans"]:
                if plan["target"] == "shot":
                    retry_counts[plan["target_id"]] = retry_counts.get(plan["target_id"], 0) + 1
            # If no shot-level retries can fix, break to avoid infinite loop
            if not any(p["target"] in ("shot", "char_refs") for p in it_resp.outputs["plans"]):
                break

        # Always render final video even if not promoted (for evidence + further repair)
        if last_renders is None:
            raise RuntimeError("No renders produced; pipeline aborted unexpectedly.")
        shot_paths = [Path(r["output_uri"]) for r in last_renders if r["output_uri"]]
        ep_out_dir = out_dir / "episodes"
        final_mp4 = episode_postprod(
            shot_mp4s=shot_paths,
            bgm_wav=Path(bgm_uri),
            out_dir=ep_out_dir,
            episode_id=ep_id,
            caption=episode["title"],
        )
        return {
            "episode_id": ep_id,
            "final_mp4": str(final_mp4),
            "qa": last_qa,
            "renders": last_renders,
            "tts_lines": last_tts,
            "cycles": cycles,
            "promoted": (last_qa["episode_report"]["promoted"] if last_qa else False),
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
