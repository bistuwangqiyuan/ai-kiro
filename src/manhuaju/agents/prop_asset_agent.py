"""PropAssetAgent — key prop reference plates (REQ-WF-003 / REQ-AGENT-v2-003)."""

from __future__ import annotations

from manhuaju.adapters.render.ffmpeg_render import render_frame
from manhuaju.core.agent_base import AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.core.seed import reference_seed


class PropAssetAgent(BaseAgent):
    name = "PropAssetAgent"

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        blueprint = req.inputs["blueprint"]
        style_sha: str = req.inputs.get("style_sha", "prop_default")
        props = blueprint.get("props") or [{"prop_id": "prop_default", "name": "默认道具"}]
        prop_refs: dict[str, list[str]] = {}
        for prop in props[:8]:
            prop_id = prop.get("prop_id") or prop.get("id") or "prop_default"
            seed = reference_seed(style_sha, prop_id)
            img = render_frame(
                width=256,
                height=256,
                location_id="prop_studio",
                mood="neutral",
                key_action=f"prop-{prop_id}",
                style_sha=style_sha[:8],
                characters=[],
                frame_seed=seed,
                char_offset_y_jitter=0,
            )
            key = f"{req.context.project_id}/04_refs/props/{prop_id}/hero.png"
            path = self.ctx.storage.path(key)
            img.save(path)
            self.ctx.provenance.record(
                artefact_uri=str(path),
                sha256="0" * 64,
                size=path.stat().st_size,
                producer_agent=self.name,
                seed=seed,
            )
            prop_refs[prop_id] = [str(path)]
        return AgentRunResponse(
            status="succeeded",
            outputs={"prop_refs": prop_refs},
            metrics={"props": float(len(prop_refs))},
        )
