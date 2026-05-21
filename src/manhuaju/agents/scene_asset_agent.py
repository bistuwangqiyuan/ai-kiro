"""SceneAssetAgent — location reference plates (REQ-WF-003 / REQ-AGENT-v2-002)."""

from __future__ import annotations

from manhuaju.adapters.render.ffmpeg_render import render_frame
from manhuaju.core.agent_base import AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.core.seed import reference_seed


class SceneAssetAgent(BaseAgent):
    name = "SceneAssetAgent"

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        blueprint = req.inputs["blueprint"]
        style_sha: str = req.inputs.get("style_sha", "scene_default")
        locations = blueprint.get("locations") or [{"location_id": "loc_default", "name": "默认场景"}]
        scene_refs: dict[str, list[str]] = {}
        for loc in locations[:6]:
            loc_id = loc.get("location_id") or loc.get("id") or "loc_default"
            urls: list[str] = []
            for view in ("wide", "medium", "detail"):
                seed = reference_seed(style_sha, f"{loc_id}:{view}")
                img = render_frame(
                    width=512,
                    height=384,
                    location_id=loc_id,
                    mood="neutral",
                    key_action=f"scene-{view}",
                    style_sha=style_sha[:8],
                    characters=[],
                    frame_seed=seed,
                    char_offset_y_jitter=0,
                )
                key = f"{req.context.project_id}/04_refs/scenes/{loc_id}/{view}.png"
                path = self.ctx.storage.path(key)
                img.save(path)
                self.ctx.provenance.record(
                    artefact_uri=str(path),
                    sha256="0" * 64,
                    size=path.stat().st_size,
                    producer_agent=self.name,
                    seed=seed,
                )
                urls.append(str(path))
            scene_refs[loc_id] = urls
        return AgentRunResponse(
            status="succeeded",
            outputs={"scene_refs": scene_refs},
            metrics={"scenes": float(len(scene_refs))},
        )
