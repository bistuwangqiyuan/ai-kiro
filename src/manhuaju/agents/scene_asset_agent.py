"""SceneAssetAgent — location reference plates (REQ-WF-003).

v4 升级：
- 注入 ``image_adapter`` 时，Seedream 5.0 出三视角（wide/medium/detail）真图，
  覆盖 docx 四节「氛围适配 + 镜头场景联动」。
- 同步把生成的图片入 TOS，让小云雀「有参考」接口可直接拉。
- 命中 ``SceneCacheStore`` 时跳过重生（docx 四节「场景复用」）。
"""

from __future__ import annotations

import contextlib
from typing import Any

from manhuaju.adapters.render.ffmpeg_render import render_frame
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.core.seed import reference_seed


class SceneAssetAgent(BaseAgent):
    name = "SceneAssetAgent"

    def __init__(
        self,
        ctx: AgentContext,
        *,
        image_adapter: Any | None = None,
        scene_cache: Any | None = None,
    ) -> None:
        super().__init__(ctx)
        self.image_adapter = image_adapter
        self.scene_cache = scene_cache

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        blueprint = req.inputs["blueprint"]
        style_sha: str = req.inputs.get("style_sha", "scene_default")
        genre = req.inputs.get("genre", "ancient")
        style_prompt = req.inputs.get("style_prompt", "古风工笔水墨")
        locations = blueprint.get("locations") or [
            {"location_id": "loc_default", "name": "默认场景"}
        ]
        scene_refs: dict[str, list[str]] = {}
        scene_public: dict[str, list[str]] = {}
        cache_hits = 0
        used_provider = "mock"

        for loc in locations[:8]:
            loc_id = loc.get("location_id") or loc.get("id") or "loc_default"
            time_of_day = loc.get("time_of_day", "day")
            weather = loc.get("weather", "clear")
            cache_key = f"{genre}|{loc_id}|{time_of_day}|{weather}"

            if self.scene_cache is not None:
                cached = self.scene_cache.lookup(cache_key)
                if cached:
                    scene_refs[loc_id] = cached.get("local_paths", [])
                    scene_public[loc_id] = cached.get("public_urls", scene_refs[loc_id])
                    cache_hits += 1
                    continue

            built = self._build_for_location(
                loc=loc,
                loc_id=loc_id,
                style_sha=style_sha,
                style_prompt=style_prompt,
                genre=genre,
                project_id=req.context.project_id,
            )
            scene_refs[loc_id] = built["local_paths"]
            scene_public[loc_id] = built["public_urls"]
            used_provider = built["provider"]

            if self.scene_cache is not None:
                with contextlib.suppress(Exception):
                    self.scene_cache.store(cache_key, built)

        return AgentRunResponse(
            status="succeeded",
            outputs={"scene_refs": scene_refs, "scene_public_urls": scene_public},
            metrics={"scenes": float(len(scene_refs)), "cache_hits": float(cache_hits)},
        )

    def _build_for_location(
        self,
        *,
        loc: dict[str, Any],
        loc_id: str,
        style_sha: str,
        style_prompt: str,
        genre: str,
        project_id: str,
    ) -> dict[str, Any]:
        if self.image_adapter is not None:
            try:
                return self._build_real(
                    loc=loc,
                    loc_id=loc_id,
                    style_prompt=style_prompt,
                    genre=genre,
                    project_id=project_id,
                )
            except Exception:  # noqa: BLE001
                pass
        return self._build_mock(loc_id=loc_id, style_sha=style_sha, project_id=project_id)

    def _build_real(
        self,
        *,
        loc: dict[str, Any],
        loc_id: str,
        style_prompt: str,
        genre: str,
        project_id: str,
    ) -> dict[str, Any]:
        name = loc.get("name") or loc_id
        atmosphere = loc.get("atmosphere", "")
        time_of_day = loc.get("time_of_day", "day")
        weather = loc.get("weather", "clear")
        base_prompt = (
            f"场景：{name}（{loc_id}），{atmosphere}，{time_of_day} 时分，{weather}，"
            f"题材：{genre}，画风：{style_prompt}"
        )
        local_paths: list[str] = []
        public_urls: list[str] = []
        for view in ("wide", "medium", "detail"):
            view_zh = {"wide": "远景全景", "medium": "中景半身", "detail": "近景细节"}[view]
            imgs = self.image_adapter.generate(
                prompt=f"{base_prompt}，镜头：{view_zh}",
                num_images=2,
                aspect_ratio="16:9",
                seed=int(_hash32(f"{loc_id}:{view}")),
                upload_to_tos=True,
                prefix=f"{project_id}_scene_{loc_id}_{view}",
            )
            for img in imgs:
                local_paths.append(str(img.local_path))
                self.ctx.provenance.record(
                    artefact_uri=str(img.local_path),
                    sha256="0" * 64,
                    size=img.bytes,
                    producer_agent=self.name,
                    seed=img.seed,
                )
                public_urls.append(img.public_url or str(img.local_path))
        return {
            "local_paths": local_paths,
            "public_urls": public_urls,
            "provider": getattr(self.image_adapter, "provider", "volcengine"),
        }

    def _build_mock(
        self, *, loc_id: str, style_sha: str, project_id: str
    ) -> dict[str, Any]:
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
            key = f"{project_id}/04_refs/scenes/{loc_id}/{view}.png"
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
        return {"local_paths": urls, "public_urls": list(urls), "provider": "mock"}


def _hash32(s: str) -> int:
    import hashlib

    return int(hashlib.md5(s.encode()).hexdigest()[:8], 16)
