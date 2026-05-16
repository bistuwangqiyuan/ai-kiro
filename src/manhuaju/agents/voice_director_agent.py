"""VoiceDirectorAgent — voice profile assignment + per-line TTS (REQ-VD-001..006)."""

from __future__ import annotations

from manhuaju.adapters.tts.mock_tts_adapter import MockTTSAdapter, TTSRequest
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.utils.canonical_json import sha256_of, to_canonical


class VoiceDirectorAgent(BaseAgent):
    name = "VoiceDirectorAgent"

    def __init__(self, ctx: AgentContext, *, tts: MockTTSAdapter) -> None:
        super().__init__(ctx)
        self.tts = tts

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        bibles = {b["char_id"]: b for b in req.inputs["bibles"]}
        script = req.inputs["script"]
        episode_id = script["episode_id"]
        line_artefacts: list[dict] = []
        for line in script["dialogues"]:
            voice = bibles.get(line["speaker_char_id"], {}).get("voice_profile", {})
            res = self.tts.synthesise(
                TTSRequest(
                    line_id=line["line_id"],
                    text=line["text"],
                    base_pitch_hz=voice.get("base_pitch_hz", 220),
                    timbre=voice.get("timbre", "neutral"),
                    energy=voice.get("energy", "medium"),
                    seconds=line["seconds"],
                )
            )
            line_artefacts.append({**res, "speaker_char_id": line["speaker_char_id"]})
            self.ctx.provenance.record(
                artefact_uri=res["wav_uri"],
                sha256="0" * 64,
                size=0,
                producer_agent=self.name,
                seed=req.seed or 0,
            )
        bundle = {
            "project_id": req.context.project_id,
            "assignments": {
                cid: bibles[cid]["voice_profile"] for cid in bibles
            },
            "pinned": True,
        }
        body = to_canonical(bundle)
        path = self.ctx.storage.write_text(
            f"{req.context.project_id}/08_voice/{episode_id}_assignments.json", body
        )
        self.ctx.provenance.record(
            artefact_uri=str(path),
            sha256=sha256_of(bundle),
            size=len(body.encode("utf-8")),
            producer_agent=self.name,
            seed=req.seed or 0,
        )
        return AgentRunResponse(
            status="succeeded",
            outputs={"lines": line_artefacts, "bundle": bundle},
            metrics={"lines": float(len(line_artefacts))},
        )
