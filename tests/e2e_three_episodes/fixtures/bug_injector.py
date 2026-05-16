"""Bug injection fixtures for REQ-PILOT-009 / REQ-PILOT-012.

Three injectable bugs:
- ``outfit_color_flip`` -> swaps a character's outfit_id mid-pipeline; this
  must trigger the Iteration Manager's consistency_refresh strategy and
  recover within one cycle.
- ``face_drift`` -> perturbs the deterministic face palette so within-shot
  ArcFace drops below 0.92.
- ``api_5xx`` -> registers a one-shot 5xx fault on the Xiaoyunque adapter
  for a specified shot id; the RenderOrchestrator should retry and recover.

Each helper is composable on a *configured pipeline*.
"""

from __future__ import annotations

from manhuaju.adapters.render.mock_xiaoyunque_adapter import MockXiaoyunqueAdapter
from manhuaju.pipelines.project_flow import ProjectPipeline


def inject_outfit_color_flip(
    pipeline: ProjectPipeline,
    *,
    char_id: str,
    target_episode_id: str,
    flipped_outfit_suffix: str = "_FLIPPED",
) -> None:
    """Patch the LLM mock so that for ``target_episode_id`` the storyboard
    pulls a *different* outfit_id for ``char_id``. The QA evaluator's
    cross-episode ArcFace will drop, the IT loop must recover."""

    original = pipeline.llm.storyboard

    def patched_storyboard(*, script: dict, style_sha: str, seed: int) -> dict:
        sb = original(script=script, style_sha=style_sha, seed=seed)
        if sb["episode_id"] == target_episode_id:
            for shot in sb["shots"]:
                for ch in shot["characters"]:
                    if ch["char_id"] == char_id:
                        ch["outfit_id"] = ch["outfit_id"] + flipped_outfit_suffix
        return sb

    pipeline.llm.storyboard = patched_storyboard  # type: ignore[assignment]


def inject_api_5xx(adapter: MockXiaoyunqueAdapter, shot_id: str) -> None:
    adapter.inject_5xx_once(shot_id)


def inject_face_drift(pipeline: ProjectPipeline, *, char_id: str) -> None:
    """Force the QA mock to lower arcface for a specific character."""
    qa = pipeline.qa_eval
    original = qa.evaluate_shot

    def patched_eval(s):
        out = original(s)
        if any(c.get("char_id") == char_id for c in s.characters):
            # bump down arcface to trigger F-003
            out["consistency"]["arcface_mean"] = 0.80
            out["consistency"]["arcface_worst"] = 0.78
            out["verdict"] = "fail"
            if not any(r.startswith("F-003") for r in out["reasons"]):
                out["reasons"].append("F-003:face_drift_injection")
        return out

    qa.evaluate_shot = patched_eval  # type: ignore[assignment]
