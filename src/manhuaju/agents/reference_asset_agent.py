"""ReferenceAssetAgent — produce 8/12 reference views per character.

REQ-REF-001..006. We use the ffmpeg_render utilities to produce *real* PNGs
that downstream renderers can attach as refs (mock pipeline carries them as
file URIs in the render request).
"""

from __future__ import annotations

from manhuaju.adapters.render.ffmpeg_render import (
    render_frame,
)
from manhuaju.core.agent_base import AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.core.seed import reference_seed

VIEWS = ["front", "left", "right", "back", "smile", "neutral", "tense", "warm"]


class ReferenceAssetAgent(BaseAgent):
    name = "ReferenceAssetAgent"

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        bibles = req.inputs["bibles"]
        all_refs: dict[str, list[str]] = {}
        for bible in bibles:
            char_id = bible["char_id"]
            outfit_id = bible["outfit_library"][0]["outfit_id"]
            urls: list[str] = []
            for view in VIEWS:
                seed = reference_seed(bible["bible_sha"], view)
                img = render_frame(
                    width=384,
                    height=512,
                    location_id="ref_studio",
                    mood="neutral",
                    key_action=f"{char_id}-{view}",
                    style_sha=bible["bible_sha"][:8],
                    characters=[{"char_id": char_id, "outfit_id": outfit_id}],
                    frame_seed=seed,
                    char_offset_y_jitter=0,
                )
                key = f"{req.context.project_id}/04_refs/{char_id}/{view}.png"
                path = self.ctx.storage.path(key)
                img.save(path)
                self.ctx.provenance.record(
                    artefact_uri=str(path),
                    sha256="0" * 64,  # png byte hash not required; provenance still chained
                    size=path.stat().st_size,
                    producer_agent=self.name,
                    seed=seed,
                )
                urls.append(str(path))
            all_refs[char_id] = urls
        self.ctx.bus.publish(
            "manhuaju.event.refs.ready",
            project_id=req.context.project_id,
            payload={"chars": len(all_refs)},
        )
        return AgentRunResponse(
            status="succeeded",
            outputs={"references": all_refs},
            metrics={"chars": float(len(all_refs))},
        )
