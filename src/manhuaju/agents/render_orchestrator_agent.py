"""RenderOrchestratorAgent — multi-candidate draw + i2v refs (REQ-RO-001..010, REQ-WF-005)."""

from __future__ import annotations

import hashlib
from typing import Any

from manhuaju.adapters.render.mock_seedance_adapter import MockSeedanceAdapter
from manhuaju.adapters.render.mock_xiaoyunque_adapter import (
    MockXiaoyunqueAdapter,
    XiaoyunqueAPIError,
)
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.core.seed import shot_seed
from manhuaju.services.seven_dim_qa import score_shot


class RenderOrchestratorAgent(BaseAgent):
    name = "RenderOrchestratorAgent"

    def __init__(
        self,
        ctx: AgentContext,
        *,
        xy: MockXiaoyunqueAdapter,
        seedance: MockSeedanceAdapter,
    ) -> None:
        super().__init__(ctx)
        self.xy = xy
        self.seedance = seedance

    def _refs_for_shot(
        self,
        shot: dict[str, Any],
        reference_map: dict[str, list[str]],
    ) -> list[str]:
        refs: list[str] = []
        for ch in shot.get("characters", []):
            cid = ch.get("char_id")
            if cid and cid in reference_map:
                refs.extend(reference_map[cid][:2])
        loc = (shot.get("palette_ref") or ["loc_default"])[0]
        scene_key = f"scene:{loc}"
        if scene_key in reference_map:
            refs.extend(reference_map[scene_key][:1])
        return refs

    def _render_one(
        self,
        *,
        shot: dict[str, Any],
        style_sha: str,
        episode_seed: int,
        resolution: str,
        fps: int,
        retry_counts: dict[str, int],
        candidate_idx: int,
        reference_images: list[str],
        req: AgentRunRequest,
    ) -> dict[str, Any]:
        shot_id = shot["shot_id"]
        seed = shot_seed(episode_seed, shot_id, retry_counts.get(shot_id, 0) + candidate_idx)
        clauses = list(shot["prompt_brief"]["clauses"])
        visual_style = str(req.inputs.get("visual_style") or "").strip()
        if visual_style:
            clauses.insert(0, visual_style)
        prompt = " | ".join(clauses)
        if reference_images:
            prompt = f"{prompt} | ref_images:{len(reference_images)}"
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        idem = f"{shot_id}:{retry_counts.get(shot_id, 0)}:{candidate_idx}:{prompt_sha[:12]}"
        output_uri: str | None = None
        degraded = False
        metadata = None
        submit_kwargs = dict(
            idem_key=idem,
            shot_id=shot_id,
            scene_id=shot["scene_id"],
            prompt=prompt,
            prompt_sha=prompt_sha,
            seed=seed,
            duration_s=int(shot["target_seconds"]),
            fps=fps,
            resolution=resolution,
            characters=shot["characters"],
            location_id=shot.get("palette_ref", ["loc_default"])[0],
            mood=shot["mood"],
            key_action=shot["key_action"],
            style_sha=style_sha,
            reference_images=reference_images,
        )
        for attempt in range(3):
            try:
                task_id = self.xy.submit(**submit_kwargs)
                snap = self.xy.poll(task_id)
                if snap["status"] == "succeeded":
                    output_uri = snap["output_uri"]
                    metadata = snap["metadata"]
                    break
            except XiaoyunqueAPIError as e:
                self.ctx.bus.publish(
                    "manhuaju.event.render.api_error",
                    project_id=req.context.project_id,
                    episode_id=req.context.episode_id,
                    shot_id=shot_id,
                    payload={"status": e.status, "attempt": attempt},
                )
                continue
        if output_uri is None:
            snap = self.seedance.synthesise(
                shot_id=shot_id,
                prompt=prompt,
                seed=seed,
                duration_s=int(shot["target_seconds"]),
                fps=fps,
                resolution=resolution,
                characters=shot["characters"],
                location_id=shot.get("palette_ref", ["loc_default"])[0],
                mood=shot["mood"],
                key_action=shot["key_action"],
                style_sha=style_sha,
            )
            output_uri = snap["output_uri"]
            metadata = snap["metadata"]
            degraded = True
        candidate = {
            "shot_id": shot_id,
            "candidate_idx": candidate_idx,
            "output_uri": output_uri,
            "metadata": metadata,
            "degraded": degraded,
            "seed": seed,
            "reference_images": reference_images,
        }
        candidate["qa7"] = score_shot(shot=shot, render=candidate, style_sha=style_sha)
        return candidate

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        # 双轨路由：当外部已经通过「短剧漫剧 Agent」原生 4 步接口出了整集成片，
        # 直接消化 ``req.inputs.manhuaju_storyboard``，跳过本地 per-shot 渲染。
        if "manhuaju_storyboard" in req.inputs:
            return self._consume_manhuaju_storyboard(req)

        storyboard = req.inputs["storyboard"]
        style_sha: str = req.inputs["style_sha"]
        episode_seed: int = req.inputs["episode_seed"]
        resolution: str = req.inputs.get("resolution", "720p")
        fps: int = int(req.inputs.get("fps", 12))
        retry_counts: dict[str, int] = req.inputs.get("retry_counts", {})
        candidates_per_shot: int = int(req.inputs.get("candidates_per_shot", 1))
        reference_map: dict[str, list[str]] = req.inputs.get("reference_map", {})

        results = []
        for shot in storyboard["shots"]:
            refs = self._refs_for_shot(shot, reference_map)
            candidates: list[dict[str, Any]] = []
            for cidx in range(max(1, candidates_per_shot)):
                candidates.append(
                    self._render_one(
                        shot=shot,
                        style_sha=style_sha,
                        episode_seed=episode_seed,
                        resolution=resolution,
                        fps=fps,
                        retry_counts=retry_counts,
                        candidate_idx=cidx,
                        reference_images=refs,
                        req=req,
                    )
                )
            best = max(
                candidates,
                key=lambda c: sum(c.get("qa7", {}).values()) if c.get("qa7") else 0.0,
            )
            results.append(
                {
                    "shot_id": shot["shot_id"],
                    "output_uri": best["output_uri"],
                    "metadata": best["metadata"],
                    "degraded": best["degraded"],
                    "seed": best["seed"],
                    "candidate_count": len(candidates),
                    "reference_images": refs,
                    "qa7": best.get("qa7"),
                }
            )
            if best["output_uri"]:
                self.ctx.provenance.record(
                    artefact_uri=best["output_uri"],
                    sha256="0" * 64,
                    size=0,
                    producer_agent=self.name,
                    seed=best["seed"],
                )
        return AgentRunResponse(
            status="succeeded",
            outputs={"shots": results},
            metrics={
                "shots": float(len(results)),
                "degraded": float(sum(1 for r in results if r["degraded"])),
            },
        )

    def _consume_manhuaju_storyboard(self, req: AgentRunRequest) -> AgentRunResponse:
        """把 ``manhuaju_agent`` pipeline 的 ``StoryboardDetail`` 转成 shot results.

        允许下游 stitch/QA 阶段无感复用本地 7 维 QA 与拼接逻辑。
        """
        storyboard: dict[str, Any] = req.inputs["manhuaju_storyboard"]
        shots_in = storyboard.get("Shots") or []
        results: list[dict[str, Any]] = []
        for s in shots_in:
            shot_id = str(s.get("ShotID") or s.get("shot_id") or "")
            video_url = str(s.get("VideoURL") or s.get("video_url") or "")
            duration_ms = int(s.get("Duration") or 0)
            metadata = {
                "width": int(s.get("Width") or 0),
                "height": int(s.get("Height") or 0),
                "format": str(s.get("Format") or "mp4"),
                "size": int(s.get("Size") or 0),
                "video_asset_id": str(s.get("VideoAssetID") or ""),
                "model_name": str(s.get("ModelName") or ""),
                "duration_s": duration_ms / 1000.0 if duration_ms else 0.0,
                "engine": "manhuaju_agent",
            }
            results.append(
                {
                    "shot_id": shot_id,
                    "output_uri": video_url,
                    "metadata": metadata,
                    "degraded": False,
                    "seed": 0,
                    "candidate_count": 1,
                    "reference_images": [],
                    "qa7": None,
                }
            )
            if video_url:
                self.ctx.provenance.record(
                    artefact_uri=video_url,
                    sha256="0" * 64,
                    size=metadata["size"],
                    producer_agent=self.name,
                    seed=0,
                )
        return AgentRunResponse(
            status="succeeded",
            outputs={"shots": results, "engine": "manhuaju_agent"},
            metrics={"shots": float(len(results)), "degraded": 0.0},
        )
