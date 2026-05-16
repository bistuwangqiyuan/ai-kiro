"""RenderOrchestratorAgent — submits + polls Xiaoyunque/Seedance (REQ-RO-001..010)."""

from __future__ import annotations

import hashlib

from manhuaju.adapters.render.mock_seedance_adapter import MockSeedanceAdapter
from manhuaju.adapters.render.mock_xiaoyunque_adapter import (
    MockXiaoyunqueAdapter,
    XiaoyunqueAPIError,
)
from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.core.seed import shot_seed


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

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        storyboard = req.inputs["storyboard"]
        style_sha: str = req.inputs["style_sha"]
        episode_seed: int = req.inputs["episode_seed"]
        resolution: str = req.inputs.get("resolution", "720p")
        fps: int = int(req.inputs.get("fps", 12))
        retry_counts: dict[str, int] = req.inputs.get("retry_counts", {})

        results = []
        for shot in storyboard["shots"]:
            shot_id = shot["shot_id"]
            seed = shot_seed(episode_seed, shot_id, retry_counts.get(shot_id, 0))
            prompt = " | ".join(shot["prompt_brief"]["clauses"])
            prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            idem = f"{shot_id}:{retry_counts.get(shot_id, 0)}:{prompt_sha[:12]}"
            output_uri: str | None = None
            degraded = False
            metadata = None
            for attempt in range(3):
                try:
                    task_id = self.xy.submit(
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
                    )
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
                # Fall back to Seedance (REQ-EXT-002 / design §8)
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
            results.append(
                {
                    "shot_id": shot_id,
                    "output_uri": output_uri,
                    "metadata": metadata,
                    "degraded": degraded,
                    "seed": seed,
                }
            )
            if output_uri:
                self.ctx.provenance.record(
                    artefact_uri=output_uri,
                    sha256="0" * 64,
                    size=0,
                    producer_agent=self.name,
                    seed=seed,
                )
        return AgentRunResponse(
            status="succeeded",
            outputs={"shots": results},
            metrics={"shots": float(len(results)), "degraded": float(sum(1 for r in results if r["degraded"]))},
        )
