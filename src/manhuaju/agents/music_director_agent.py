"""MusicDirectorAgent — BGM + mix cues (REQ-MD-001..006)."""

from __future__ import annotations

from manhuaju.adapters.music.mock_music_adapter import MockMusicAdapter
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent


class MusicDirectorAgent(BaseAgent):
    name = "MusicDirectorAgent"

    def __init__(self, ctx: AgentContext, *, music: MockMusicAdapter) -> None:
        super().__init__(ctx)
        self.music = music

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        episode_id = req.inputs["episode_id"]
        seconds: float = req.inputs["target_seconds"]
        mood = req.inputs.get("mood", "tense")
        bgm = self.music.render_bgm(
            episode_id=episode_id, seconds=seconds, mood=mood, seed=req.seed or 0
        )
        self.ctx.provenance.record(
            artefact_uri=bgm["bgm_uri"],
            sha256="0" * 64,
            size=0,
            producer_agent=self.name,
            seed=req.seed or 0,
        )
        return AgentRunResponse(
            status="succeeded",
            outputs={"bgm": bgm},
            metrics={"duration_s": float(seconds)},
        )
