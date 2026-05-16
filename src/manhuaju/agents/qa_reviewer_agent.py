"""QAReviewerAgent — per-shot + per-episode QA (REQ-QA-001..010)."""

from __future__ import annotations

from manhuaju.adapters.qa.mock_qa_evaluator_adapter import MockQAEvaluatorAdapter, ShotInputs
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent


class QAReviewerAgent(BaseAgent):
    name = "QAReviewerAgent"

    def __init__(self, ctx: AgentContext, *, qa: MockQAEvaluatorAdapter) -> None:
        super().__init__(ctx)
        self.qa = qa

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        storyboard = req.inputs["storyboard"]
        renders = {r["shot_id"]: r for r in req.inputs["renders"]}
        tts_lines = {line["line_id"]: line for line in req.inputs.get("tts_lines", [])}
        seed = req.seed or 1

        shot_reports = []
        for shot in storyboard["shots"]:
            r = renders.get(shot["shot_id"], {})
            si = ShotInputs(
                shot_id=shot["shot_id"],
                sequence_index=shot["sequence_index"],
                seed=seed + shot["sequence_index"],
                characters=shot["characters"],
                target_seconds=shot["target_seconds"],
                duration_s=float((r.get("metadata") or {}).get("duration_s", shot["target_seconds"])),
                fps=int((r.get("metadata") or {}).get("fps", 24)),
                intent=shot.get("key_emotion", "neutral"),
                mood=shot.get("mood", "neutral"),
            )
            shot_reports.append(self.qa.evaluate_shot(si))

        # Episode-level UTMOS aggregate from TTS lines
        utmos_vals = []
        for li_id, line_artefact in tts_lines.items():
            v = line_artefact.get("voice_profile", {})
            utmos_vals.append(
                self.qa.evaluate_tts(
                    line_id=li_id,
                    seconds=float(line_artefact.get("duration_s", 1.5)),
                    energy=v.get("energy", "medium"),
                    timbre=v.get("timbre", "neutral"),
                    seed=seed,
                )
            )
        utmos_mean = sum(utmos_vals) / len(utmos_vals) if utmos_vals else 4.1

        passes = sum(1 for r in shot_reports if r["verdict"] == "pass")
        pass_rate = passes / max(1, len(shot_reports))
        episode_report = {
            "episode_id": storyboard["episode_id"],
            "shots": [s["shot_id"] for s in shot_reports],
            "pass_rate": pass_rate,
            "aesthetic_mean": (
                sum(s["aesthetic"]["laion_mean"] for s in shot_reports) / max(1, len(shot_reports))
            ),
            "arcface_mean": (
                sum(s["consistency"]["arcface_mean"] for s in shot_reports) / max(1, len(shot_reports))
            ),
            "vbench_mean": (
                sum(s["consistency"]["vbench_subject"] for s in shot_reports) / max(1, len(shot_reports))
            ),
            "utmos_mean": utmos_mean,
            "syncnet_offset_max": (
                max((abs(s["sync"]["syncnet_offset_frames"]) for s in shot_reports), default=0.0)
            ),
            "promoted": pass_rate >= 0.95,
            "reasons": [],
        }
        return AgentRunResponse(
            status="succeeded",
            outputs={"shot_reports": shot_reports, "episode_report": episode_report},
            metrics={
                "pass_rate": pass_rate,
                "aesthetic_mean": episode_report["aesthetic_mean"],
                "arcface_mean": episode_report["arcface_mean"],
                "vbench_mean": episode_report["vbench_mean"],
                "utmos_mean": utmos_mean,
            },
        )
