"""Live smoke probes for each Real* adapter.

Each probe is bounded to <60s. Run with:
    $env:PYTHONPATH = "src"; python tools/smoke/live_probes.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from manhuaju.adapters.embedding.real_dashscope_embedding_adapter import (
    RealDashScopeEmbeddingAdapter,
)
from manhuaju.adapters.llm.real_llm_adapter import RealLLMAdapter
from manhuaju.adapters.qa.mock_qa_evaluator_adapter import ShotInputs
from manhuaju.adapters.qa.real_qa_proxy_adapter import RealQAProxyAdapter
from manhuaju.adapters.render.real_wanx_adapter import RealWanXAdapter
from manhuaju.adapters.tts.mock_tts_adapter import TTSRequest
from manhuaju.adapters.tts.real_dashscope_tts_adapter import RealDashScopeTTSAdapter
from manhuaju.core.cost_tracker import CostTracker
from manhuaju.core.provider_settings import get_provider_settings


def section(name: str) -> None:
    print(f"\n=== {name} ===", flush=True)


def main() -> int:
    settings = get_provider_settings()
    cost = CostTracker()
    out_dir = Path("./tools/smoke/_artefacts")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. LLM
    section("LLM (real_llm_adapter.chat)")
    llm = RealLLMAdapter(settings=settings, cost=cost, config={"request_timeout_s": 20})
    t0 = time.time()
    text = llm.chat(
        messages=[
            {"role": "system", "content": "Return one JSON object."},
            {"role": "user", "content": 'Return {"hello":"world"}'},
        ],
        op="probe.llm",
        max_tokens=32,
        temperature=0.0,
    )
    print(f"  result={text!r}  ({time.time() - t0:.1f}s)")

    # 2. Embedding
    section("Embedding (DashScope text-embedding-v3)")
    if settings.dashscope_key:
        emb = RealDashScopeEmbeddingAdapter(settings=settings, cost=cost)
        t0 = time.time()
        v = emb.embed("hello world 你好")
        print(f"  dim={len(v)}  L2={sum(x*x for x in v)**0.5:.3f}  ({time.time() - t0:.1f}s)")
    else:
        print("  skipped: no DASHSCOPE_API_KEY")

    # 3. TTS (CosyVoice via SDK)
    section("TTS (CosyVoice via dashscope SDK)")
    if settings.dashscope_key:
        tts = RealDashScopeTTSAdapter(
            settings=settings,
            cost=cost,
            artefacts_root=out_dir / "tts",
            mock_fallback=None,
        )
        t0 = time.time()
        try:
            r = tts.synthesise(
                TTSRequest(line_id="probe", text="你好世界", seconds=2.0)
            )
            print(f"  wav={r['wav_uri']}  dur={r['duration_s']:.2f}s  ({time.time() - t0:.1f}s)")
        except Exception as e:
            print(f"  TTS failed: {type(e).__name__}: {e}")
    else:
        print("  skipped: no DASHSCOPE_API_KEY")

    # 4. WanX video — only submit, do not poll long.
    section("WanX submit (DashScope video-generation)")
    if settings.dashscope_key:
        wanx = RealWanXAdapter(
            settings=settings,
            cost=cost,
            artefacts_root=out_dir / "video",
            config={"poll_interval_s": 5, "max_poll_s": 30},
        )
        t0 = time.time()
        task_id = wanx.submit(
            idem_key="probe-1",
            shot_id="probe_sh01",
            scene_id="probe_sc01",
            prompt="A cinematic 2D manga drama: a young woman in a futuristic city",
            prompt_sha="probe",
            seed=42,
            duration_s=5,
            fps=24,
            resolution="720p",
            characters=[{"name": "Yunque", "archetype": "lead"}],
            location_id="city",
            mood="determined",
            key_action="walks forward",
            style_sha="probe",
            model_tier="pro",
        )
        print(f"  task_id={task_id}  submit_time={time.time() - t0:.1f}s")
        # quick poll once (don't wait long)
        poll_t0 = time.time()
        snap = wanx.poll(task_id)
        print(f"  poll_status={snap['status']}  poll_time={time.time() - poll_t0:.1f}s")
    else:
        print("  skipped: no DASHSCOPE_API_KEY")

    # 5. QA proxy (LLM-as-judge for one shot)
    section("QA proxy (LLM-as-judge aesthetic)")
    qa = RealQAProxyAdapter(llm=llm, cost=cost)
    t0 = time.time()
    rep = qa.evaluate_shot(
        ShotInputs(
            shot_id="probe_sh01",
            sequence_index=0,
            seed=42,
            characters=[{"char_id": "yunque", "outfit_id": "default"}],
            target_seconds=5,
            duration_s=5.0,
            fps=24,
            intent="introduce",
            mood="determined",
        )
    )
    print(
        f"  laion={rep['aesthetic']['laion_mean']:.2f} (judge={rep['aesthetic'].get('judge_score')})  "
        f"verdict={rep['verdict']}  ({time.time() - t0:.1f}s)"
    )

    section("Cost summary")
    print(json.dumps(cost.summary(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
