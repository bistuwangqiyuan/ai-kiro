"""ReferenceAssetAgent — produce 8/14 reference views per character.

v4 ★ 升级（Shell 2 角色资产库）:
- 当注入了 ``image_adapter``（Seedream 5.0 / Jimeng 4.6）时，走真图生产线：
  Seedream 出 8 张多角度（正/45/侧/背 + 4 表情），Jimeng 出 6 张姿态/服装变体。
  共 14 张参考图，覆盖 tech.md 防线 2 「同一组 reference_images 全集复用」。
- 当 image_adapter 不可用（mock 模式）时，回退到旧的 ffmpeg_render Pillow 占位。

REQ-REF-001..006 + REQ-V4-CONS-2 (跨集一致性防线 2)
"""

from __future__ import annotations

import contextlib
from typing import Any

from manhuaju.adapters.render.ffmpeg_render import render_frame
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.core.seed import reference_seed

VIEWS = ["front", "left", "right", "back", "smile", "neutral", "tense", "warm"]


class ReferenceAssetAgent(BaseAgent):
    name = "ReferenceAssetAgent"

    def __init__(self, ctx: AgentContext, *, image_adapter: Any | None = None) -> None:
        super().__init__(ctx)
        self.image_adapter = image_adapter

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        bibles = req.inputs["bibles"]
        genre = req.inputs.get("genre", "ancient")
        style_prompt = req.inputs.get("style_prompt", "古风工笔水墨")
        all_refs: dict[str, list[str]] = {}
        all_urls: dict[str, list[str]] = {}
        used_provider = "mock"

        for bible in bibles:
            char_id = bible["char_id"]
            outfit_id = bible["outfit_library"][0]["outfit_id"]
            urls = self._build_for_character(
                bible=bible,
                outfit_id=outfit_id,
                char_id=char_id,
                project_id=req.context.project_id,
                genre=genre,
                style_prompt=style_prompt,
            )
            all_refs[char_id] = urls["local_paths"]
            all_urls[char_id] = urls["public_urls"]
            used_provider = urls["provider"]

        self.ctx.bus.publish(
            "manhuaju.event.refs.ready",
            project_id=req.context.project_id,
            payload={"chars": len(all_refs), "provider": used_provider},
        )

        manifest_key = f"{req.context.project_id}/04_refs/asset_manifest.json"
        manifest: dict[str, Any] = {
            "characters": all_refs,
            "character_public_urls": all_urls,
            "scenes": req.inputs.get("scene_refs", {}),
            "props": req.inputs.get("prop_refs", {}),
            "provider": used_provider,
        }
        self.ctx.storage.write_json(manifest_key, manifest)

        return AgentRunResponse(
            status="succeeded",
            outputs={
                "references": all_refs,
                "references_public_urls": all_urls,
                "asset_manifest": manifest,
            },
            metrics={"chars": float(len(all_refs))},
        )

    # ----- per-character builder -----
    def _build_for_character(
        self,
        *,
        bible: dict[str, Any],
        outfit_id: str,
        char_id: str,
        project_id: str,
        genre: str,
        style_prompt: str,
    ) -> dict[str, Any]:
        if self.image_adapter is not None:
            try:
                return self._build_real(
                    bible=bible,
                    char_id=char_id,
                    outfit_id=outfit_id,
                    project_id=project_id,
                    genre=genre,
                    style_prompt=style_prompt,
                )
            except Exception:  # noqa: BLE001
                # Fall through to mock
                pass
        return self._build_mock(
            bible=bible, char_id=char_id, outfit_id=outfit_id, project_id=project_id
        )

    def _build_real(
        self,
        *,
        bible: dict[str, Any],
        char_id: str,
        outfit_id: str,
        project_id: str,
        genre: str,
        style_prompt: str,
    ) -> dict[str, Any]:
        attribute_block = _bible_to_prompt_zh(bible, style_prompt=style_prompt, genre=genre)
        # Seedream 出 8 张主组
        primary = self.image_adapter.generate_group(
            prompt=attribute_block,
            num_images=8,
            aspect_ratio="3:4",
            seed=int(_hash32(f"{char_id}:{outfit_id}:primary")),
            upload_to_tos=True,
            prefix=f"{project_id}_{char_id}",
        )
        # Jimeng 出 6 张姿态/服装变体（用 Seedream 前两张做引导参考）
        variants: list[Any] = []
        with contextlib.suppress(Exception):
            ref_paths = [str(p.local_path) for p in primary[:2]]
            if hasattr(self.image_adapter, "_variant_adapter"):
                variants = self.image_adapter._variant_adapter.generate_with_reference(
                    prompt=attribute_block
                    + "\n姿态：站立 / 行走 / 持剑 / 盘坐 / 出招 / 受伤。服装与发型保持一致。",
                    reference_images=ref_paths,
                    num_images=6,
                    aspect_ratio="3:4",
                    seed=int(_hash32(f"{char_id}:{outfit_id}:variant")),
                    upload_to_tos=True,
                    prefix=f"{project_id}_{char_id}_variant",
                )
        all_images = list(primary) + list(variants)
        local_paths: list[str] = []
        public_urls: list[str] = []
        for img in all_images:
            local_paths.append(str(img.local_path))
            self.ctx.provenance.record(
                artefact_uri=str(img.local_path),
                sha256="0" * 64,
                size=img.bytes,
                producer_agent=self.name,
                seed=img.seed,
            )
            if img.public_url:
                public_urls.append(img.public_url)
            else:
                public_urls.append(str(img.local_path))
        return {
            "local_paths": local_paths,
            "public_urls": public_urls,
            "provider": getattr(self.image_adapter, "provider", "volcengine"),
        }

    def _build_mock(
        self,
        *,
        bible: dict[str, Any],
        char_id: str,
        outfit_id: str,
        project_id: str,
    ) -> dict[str, Any]:
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
            key = f"{project_id}/04_refs/{char_id}/{view}.png"
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


def _bible_to_prompt_zh(bible: dict[str, Any], *, style_prompt: str, genre: str) -> str:
    """把 CharacterBible 转成 Seedream/Jimeng 的中文长 prompt。"""
    appearance = bible.get("appearance", {}) or {}
    outfit = (bible.get("outfit_library") or [{}])[0]
    parts = [
        f"角色：{bible.get('display_name') or bible.get('name') or bible['char_id']}",
        f"年龄：{appearance.get('age', '青年')}",
        f"身材：{appearance.get('body', '匀称')}",
        f"五官：{appearance.get('face', '俊朗')}",
        f"发型：{appearance.get('hair', '黑色长发')}",
        f"瞳色：{appearance.get('eye_color', '深邃')}",
        f"服饰：{outfit.get('description', '古风长袍')}",
        f"配饰：{outfit.get('accessories', '')}",
        f"题材：{genre}",
        f"画风：{style_prompt}",
        "高清，全身可见，单人，无背景干扰",
    ]
    return "，".join(p for p in parts if p.split("：", 1)[-1].strip())


def _hash32(s: str) -> int:
    import hashlib

    return int(hashlib.md5(s.encode()).hexdigest()[:8], 16)
