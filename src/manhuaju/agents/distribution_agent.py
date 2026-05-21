"""DistributionAgent — export MP4/cover/copy for platforms (REQ-DIST-001..004)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from manhuaju.core.agent_base import AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.services.distribution import (
    apply_watermark,
    extract_cover,
    transcode_for_platform,
    write_copy_pack,
)


class DistributionAgent(BaseAgent):
    name = "DistributionAgent"

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        episode_id: str = req.inputs["episode_id"]
        source_mp4 = Path(req.inputs["source_mp4"])
        platform: str = req.inputs.get("platform", "douyin")
        title: str = req.inputs.get("title", episode_id)
        synopsis: str = req.inputs.get("synopsis", "")
        watermark: bool = bool(req.inputs.get("watermark", False))
        export_root = self.ctx.storage.path(f"{req.context.project_id}/export")
        export_root.mkdir(parents=True, exist_ok=True)

        out_mp4 = export_root / f"{episode_id}_{platform}.mp4"
        transcode_for_platform(source_mp4, out_mp4, platform)
        if watermark:
            wm_path = export_root / f"{episode_id}_{platform}_wm.mp4"
            apply_watermark(out_mp4, wm_path)
            out_mp4 = wm_path

        cover = export_root / f"{episode_id}_cover.png"
        extract_cover(out_mp4, cover)

        copy_path = export_root / f"{episode_id}_copy_pack.json"
        write_copy_pack(
            copy_path,
            title=title,
            synopsis=synopsis or title,
            hooks=[f"第{episode_id}集高能来袭", "AI漫剧Autopilot"],
        )

        manifest = {
            "episode_id": episode_id,
            "platform": platform,
            "mp4": str(out_mp4),
            "cover": str(cover),
            "copy_pack": str(copy_path),
        }
        manifest_path = export_root / f"{episode_id}_manifest.json"
        manifest_path.write_text(
            __import__("json").dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.ctx.bus.publish(
            "manhuaju.event.distribution.exported",
            project_id=req.context.project_id,
            episode_id=episode_id,
            payload=manifest,
        )
        return AgentRunResponse(
            status="succeeded",
            outputs={"manifest": manifest},
            metrics={"exports": 1.0},
        )
