"""PropAssetAgent — key prop reference plates (REQ-WF-003).

v4 升级：可选 image_adapter（Jimeng 4.6）真图。
"""

from __future__ import annotations

from typing import Any

from manhuaju.adapters.render.ffmpeg_render import render_frame
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.core.seed import reference_seed


class PropAssetAgent(BaseAgent):
    name = "PropAssetAgent"

    def __init__(self, ctx: AgentContext, *, image_adapter: Any | None = None) -> None:
        super().__init__(ctx)
        self.image_adapter = image_adapter

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        blueprint = req.inputs["blueprint"]
        style_sha: str = req.inputs.get("style_sha", "prop_default")
        style_prompt = req.inputs.get("style_prompt", "古风工笔水墨")
        genre = req.inputs.get("genre", "ancient")
        props = blueprint.get("props") or [{"prop_id": "prop_default", "name": "默认道具"}]
        prop_refs: dict[str, list[str]] = {}
        prop_public: dict[str, list[str]] = {}

        for prop in props[:12]:
            prop_id = prop.get("prop_id") or prop.get("id") or "prop_default"
            name = prop.get("name") or prop_id
            paths, urls = self._build_one(
                prop_id=prop_id,
                name=name,
                description=prop.get("description", ""),
                style_sha=style_sha,
                style_prompt=style_prompt,
                genre=genre,
                project_id=req.context.project_id,
            )
            prop_refs[prop_id] = paths
            prop_public[prop_id] = urls

        return AgentRunResponse(
            status="succeeded",
            outputs={"prop_refs": prop_refs, "prop_public_urls": prop_public},
            metrics={"props": float(len(prop_refs))},
        )

    def _build_one(
        self,
        *,
        prop_id: str,
        name: str,
        description: str,
        style_sha: str,
        style_prompt: str,
        genre: str,
        project_id: str,
    ) -> tuple[list[str], list[str]]:
        if self.image_adapter is not None:
            try:
                prompt = (
                    f"道具：{name}（{prop_id}）。{description}。"
                    f"题材：{genre}。画风：{style_prompt}。纯白背景，居中，高清"
                )
                imgs = self.image_adapter.generate(
                    prompt=prompt,
                    num_images=1,
                    aspect_ratio="1:1",
                    seed=int(_hash32(f"{prop_id}")),
                    upload_to_tos=True,
                    prefix=f"{project_id}_prop_{prop_id}",
                )
                if imgs:
                    paths = [str(i.local_path) for i in imgs]
                    urls = [i.public_url or str(i.local_path) for i in imgs]
                    for i in imgs:
                        self.ctx.provenance.record(
                            artefact_uri=str(i.local_path),
                            sha256="0" * 64,
                            size=i.bytes,
                            producer_agent=self.name,
                            seed=i.seed,
                        )
                    return paths, urls
            except Exception:  # noqa: BLE001
                pass
        # mock
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
        key = f"{project_id}/04_refs/props/{prop_id}/hero.png"
        path = self.ctx.storage.path(key)
        img.save(path)
        self.ctx.provenance.record(
            artefact_uri=str(path),
            sha256="0" * 64,
            size=path.stat().st_size,
            producer_agent=self.name,
            seed=seed,
        )
        return [str(path)], [str(path)]


def _hash32(s: str) -> int:
    import hashlib

    return int(hashlib.md5(s.encode()).hexdigest()[:8], 16)
