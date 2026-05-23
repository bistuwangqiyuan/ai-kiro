"""Smoke-test all v4 provider API keys.

Run:
    python -m scripts.smoke_keys            # plain ascii table
    python -m scripts.smoke_keys --json     # machine-readable
    python -m scripts.smoke_keys --strict   # exit 1 if any required key missing

Validates connectivity (1 lightweight ping per provider). The script never
reveals key bodies — only masked first/last 4 chars.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any

from manhuaju.core.provider_settings import get_provider_settings


@dataclass
class ProbeResult:
    name: str
    enabled: bool
    ok: bool
    latency_ms: int
    detail: str
    required: bool = False


def _probe_anthropic(key: str) -> tuple[bool, int, str]:
    if not key:
        return False, 0, "no ANTHROPIC_API_KEY"
    try:
        import httpx

        t0 = time.time()
        with httpx.Client(timeout=15) as c:
            r = c.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-opus-4-20250514",
                    "max_tokens": 8,
                    "messages": [{"role": "user", "content": "ping"}],
                },
            )
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            return True, ms, "ok"
        return False, ms, f"HTTP {r.status_code}: {r.text[:120]}"
    except Exception as e:  # noqa: BLE001
        return False, 0, f"{type(e).__name__}: {e}"


def _probe_dashscope(key: str) -> tuple[bool, int, str]:
    if not key:
        return False, 0, "no DASHSCOPE_API_KEY"
    try:
        import httpx

        t0 = time.time()
        with httpx.Client(timeout=15) as c:
            r = c.post(
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "qwen-plus",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 4,
                },
            )
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            return True, ms, "ok"
        return False, ms, f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        return False, 0, f"{type(e).__name__}: {e}"


def _probe_volcengine_ark(key: str) -> tuple[bool, int, str]:
    if not key:
        return False, 0, "no VOLCENGINE_ARK_API_KEY / VOLCENGINE_API_KEY"
    try:
        import httpx

        t0 = time.time()
        with httpx.Client(timeout=15) as c:
            r = c.post(
                "https://ark.cn-beijing.volces.com/api/v3/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": "doubao-seed-1-6-250615",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 4,
                },
            )
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            return True, ms, "ok"
        return False, ms, f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        return False, 0, f"{type(e).__name__}: {e}"


def _probe_volcengine_visual(ak: str, sk: str, region: str) -> tuple[bool, int, str]:
    if not (ak and sk):
        return False, 0, "no VOLCENGINE_VISUAL_AK/SK"
    try:
        from volcengine.visual.VisualService import VisualService  # type: ignore[import-untyped]

        t0 = time.time()
        svc = VisualService()
        svc.set_ak(ak)
        svc.set_sk(sk)
        # Use a known-cheap probe: query a nonexistent task — expects logical 4xx but
        # AK/SK valid means we'll get a parseable error response (not a 401-style auth error).
        try:
            svc.cv_sync2async_get_result({"req_key": "skylark_video_agent_v2_with_ref",
                                          "task_id": "smoke_probe_invalid"})
            ms = int((time.time() - t0) * 1000)
            return True, ms, "ok (probe returned)"
        except Exception as inner:  # noqa: BLE001
            ms = int((time.time() - t0) * 1000)
            msg = str(inner)
            if "task" in msg.lower() or "not exist" in msg.lower() or "found" in msg.lower():
                return True, ms, "ok (expected task-not-found)"
            return False, ms, f"unexpected: {msg[:120]}"
    except ImportError:
        return False, 0, "volcengine-python-sdk not installed (pip install volcengine-python-sdk)"
    except Exception as e:  # noqa: BLE001
        return False, 0, f"{type(e).__name__}: {e}"


def _probe_tos(ak: str, sk: str, endpoint: str, bucket: str, region: str) -> tuple[bool, int, str]:
    if not (ak and sk and bucket):
        return False, 0, "no VOLCENGINE_TOS_*"
    try:
        import tos  # type: ignore[import-untyped]

        t0 = time.time()
        client = tos.TosClientV2(ak, sk, endpoint, region)
        client.head_bucket(bucket)
        ms = int((time.time() - t0) * 1000)
        return True, ms, f"ok bucket={bucket}"
    except ImportError:
        return False, 0, "tos sdk not installed (pip install tos)"
    except Exception as e:  # noqa: BLE001
        return False, 0, f"{type(e).__name__}: {str(e)[:120]}"


def _probe_elevenlabs(key: str) -> tuple[bool, int, str]:
    if not key:
        return False, 0, "no ELEVENLABS_API_KEY"
    try:
        import httpx

        t0 = time.time()
        with httpx.Client(timeout=15) as c:
            r = c.get("https://api.elevenlabs.io/v1/user", headers={"xi-api-key": key})
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            data = r.json()
            char = (data.get("subscription") or {}).get("character_count", 0)
            limit = (data.get("subscription") or {}).get("character_limit", 0)
            return True, ms, f"ok used={char}/{limit}"
        return False, ms, f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        return False, 0, f"{type(e).__name__}: {e}"


def _probe_fal(key: str) -> tuple[bool, int, str]:
    if not key:
        return False, 0, "no FAL_KEY"
    try:
        import httpx

        t0 = time.time()
        with httpx.Client(timeout=15) as c:
            # fal.ai 不暴露 GET 探针；用 HEAD 验证 Auth header 通过
            r = c.head(
                "https://queue.fal.run/fal-ai/wan-2.7/flf",
                headers={"Authorization": f"Key {key}"},
            )
        ms = int((time.time() - t0) * 1000)
        if r.status_code in (200, 404, 405):  # 405 = HEAD not allowed but auth passed
            return True, ms, f"ok status={r.status_code}"
        return False, ms, f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        return False, 0, f"{type(e).__name__}: {e}"


def _probe_openai_compat(name: str, base_url: str, key: str, model: str) -> tuple[bool, int, str]:
    if not key:
        return False, 0, f"no key for {name}"
    try:
        import httpx

        t0 = time.time()
        with httpx.Client(timeout=15) as c:
            r = c.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 4},
            )
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            return True, ms, "ok"
        return False, ms, f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        return False, 0, f"{type(e).__name__}: {e}"


def run_probes() -> list[ProbeResult]:
    s = get_provider_settings(refresh=True)
    results: list[ProbeResult] = []

    # ---- Required for v4 fast-path ----
    ok, ms, det = _probe_anthropic(s.anthropic_key)
    results.append(ProbeResult("Anthropic Claude Opus 4 (Shell 1)", bool(s.anthropic_key), ok, ms, det, required=True))

    ok, ms, det = _probe_volcengine_visual(s.volcengine_visual_ak, s.volcengine_visual_sk, s.volcengine_visual_region)
    results.append(ProbeResult("Volcengine Visual SDK (Shell 2+3 ★)", s.has_xiaoyunque, ok, ms, det, required=True))

    ok, ms, det = _probe_volcengine_ark(s.volcengine_ark_key)
    results.append(ProbeResult("Volcengine Ark (Doubao Seed 1.6 + Seedance, Shell 4)", s.has_doubao_vlm, ok, ms, det, required=True))

    ok, ms, det = _probe_tos(s.tos.ak, s.tos.sk, s.tos.endpoint, s.tos.bucket, s.tos.region)
    results.append(ProbeResult("Volcengine TOS (对象存储)", s.has_tos, ok, ms, det, required=True))

    ok, ms, det = _probe_elevenlabs(s.elevenlabs_key)
    results.append(ProbeResult("ElevenLabs (Shell 5 Music+SFX)", s.has_elevenlabs, ok, ms, det, required=False))

    ok, ms, det = _probe_fal(s.fal_key)
    results.append(ProbeResult("fal.ai Wan 2.7 FLF (Shell 4)", s.has_fal, ok, ms, det, required=False))

    # ---- Fallback chain ----
    ok, ms, det = _probe_dashscope(s.dashscope_key)
    results.append(ProbeResult("DashScope (WanX/CosyVoice 兜底)", bool(s.dashscope_key), ok, ms, det, required=False))

    # LLM chain (skip ones already probed)
    seen_names = {"anthropic", "volcengine", "dashscope"}
    for ep in s.llm_endpoints:
        if ep.name in seen_names:
            continue
        ok, ms, det = _probe_openai_compat(ep.name, ep.base_url, ep.api_key, ep.default_model)
        results.append(ProbeResult(f"LLM chain · {ep.name}", True, ok, ms, det, required=False))

    return results


def render_table(results: list[ProbeResult]) -> str:
    rows = ["{:<55} {:<6} {:<6} {:>9} {}".format("Provider", "ENABL", "OK", "lat(ms)", "detail")]
    rows.append("-" * 115)
    for r in results:
        rows.append(
            "{:<55} {:<6} {:<6} {:>9} {}".format(
                r.name + (" ★" if r.required else ""),
                "Y" if r.enabled else "N",
                "Y" if r.ok else ("-" if not r.enabled else "N"),
                str(r.latency_ms) if r.latency_ms else "-",
                r.detail,
            )
        )
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="AI 漫剧 v4 — provider key smoke test")
    parser.add_argument("--json", action="store_true", help="output JSON")
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 if any *required* provider missing or unhealthy")
    args = parser.parse_args()

    results = run_probes()
    if args.json:
        print(json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2))
    else:
        print(render_table(results))
        print()
        print("★ = required for v4 fast-path (小云雀 Agent 2.0 + Claude Opus 4 + TOS + Ark VLM)")

    if args.strict:
        bad = [r for r in results if r.required and not r.ok]
        if bad:
            print(f"\nFAIL: {len(bad)} required provider(s) missing/unhealthy:", file=sys.stderr)
            for r in bad:
                print(f"  - {r.name}: {r.detail}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
