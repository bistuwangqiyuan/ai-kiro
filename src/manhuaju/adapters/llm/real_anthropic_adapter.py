"""Real Anthropic Claude Opus 4 adapter — Shell 1 编剧大脑 ★.

3 个核心方法（tech.md 二/三节）：

- ``extract_events(novel_text)`` —— 把整本小说压缩成事件列表，每章 1-3 条主线。
- ``write_episodes(events, n=30, episode_seconds=75)`` —— 写 30 集草稿，结构
  = 0-3s 钩子 + 3-50s 冲突 + 50-65s 反转 + 65-75s 悬念。
- ``format_for_xiaoyunque(scripts, char_bibles, scenes)`` —— 改写成「小云雀友好模板」：
    * 每集首部插入完整人物设定块 + 场景设定块（防线 1）。
    * 每个分镜标注景别、时长、动作、情绪、对白/旁白。

Graceful fallback：未配 ``ANTHROPIC_API_KEY`` → 委托给现有 ``RealLLMAdapter``
（DashScope qwen-plus / Volcengine doubao-seed-1.6 等），保证 schema 不变。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from manhuaju.core.cost_tracker import CostEntry, CostTracker, now_s
from manhuaju.core.provider_settings import ProviderSettings

API_BASE = "https://api.anthropic.com/v1"
DEFAULT_MODEL = "claude-opus-4-20250514"
ANTHROPIC_VERSION = "2023-06-01"


@dataclass
class LLMResult:
    text: str
    parsed: Any
    model: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    provider: str = "anthropic"
    success: bool = True
    error: str | None = None


class RealAnthropicLLMAdapter:
    """Claude Opus 4 native adapter. Use as 1st-priority LLM endpoint."""

    name = "RealAnthropicLLMAdapter"
    provider = "anthropic"

    def __init__(
        self,
        *,
        settings: ProviderSettings,
        cost: CostTracker,
        config: dict[str, Any] | None = None,
        mock_fallback: Any | None = None,
    ) -> None:
        self._settings = settings
        self._cost = cost
        self._cfg = config or {}
        self._model = self._cfg.get("novel_model") or DEFAULT_MODEL
        self._timeout_s = float(self._cfg.get("request_timeout_s", 120))
        self._max_retries = int(self._cfg.get("max_retries", 3))
        self.mock_fallback = mock_fallback

    @property
    def available(self) -> bool:
        return bool(self._settings.anthropic_key)

    # ==================================================================
    # Public methods (tech.md 编剧管线)
    # ==================================================================
    def extract_events(self, novel_text: str, *, max_chapters: int = 50) -> LLMResult:
        sys_prompt = (
            "你是金牌网文编辑。把整本小说按主线压缩成事件列表，"
            "每章 1-3 条核心事件，过滤水文。"
            "只返回 JSON：{\"events\":[{\"chapter\":int,\"order\":int,\"title\":str,"
            "\"summary\":str,\"characters\":[str],\"location\":str,\"emotion\":str}]}。"
        )
        user = f"小说原文（共 {len(novel_text):,} 字）：\n\n{novel_text[:480_000]}"
        return self._complete_json(sys_prompt, user, max_tokens=8192, label="extract_events")

    def write_episodes(
        self,
        events: list[dict[str, Any]] | str,
        *,
        n: int = 30,
        episode_seconds: int = 75,
        genre: str = "ancient",
    ) -> LLMResult:
        events_text = events if isinstance(events, str) else json.dumps(events, ensure_ascii=False)
        sys_prompt = (
            f"你是漫剧金牌编剧。基于事件列表写 {n} 集剧本，每集 {episode_seconds} 秒。"
            f"结构 = 钩子(0-3s) + 冲突(3-{episode_seconds-25}s) + 反转({episode_seconds-25}-{episode_seconds-10}s) "
            f"+ 悬念({episode_seconds-10}-{episode_seconds}s)。题材：{genre}。"
            "返回 JSON：{\"episodes\":[{\"episode_id\":\"ep01\",\"title\":str,\"hook\":str,"
            "\"conflict\":str,\"twist\":str,\"cliffhanger\":str,"
            "\"scenes\":[{\"scene_id\":str,\"location\":str,\"time\":str,"
            "\"characters\":[str],\"emotion\":str,\"beats\":[str]}]}]}。"
        )
        return self._complete_json(
            sys_prompt, events_text, max_tokens=16000, label="write_episodes"
        )

    def format_for_xiaoyunque(
        self,
        *,
        episode_draft: dict[str, Any],
        character_bibles: list[dict[str, Any]],
        scenes: list[dict[str, Any]],
        episode_seconds: int = 75,
        genre: str = "ancient",
    ) -> LLMResult:
        """tech.md「小云雀友好剧本模板」生成。

        强制：
        - 每集开头完整 [人物设定（必填，全集生效）] 块；
        - 每集开头完整 [场景设定] 块；
        - [第 N 集分镜建议] 列出每个镜头（景别 + 时长秒 + 动作 + 情绪 + 对白）。
        """
        sys_prompt = (
            "你是漫剧分镜师。把分集草稿改写成「小云雀 Agent 2.0 友好剧本模板」。"
            "重要：每一集都必须重复完整的『人物设定块』和『场景设定块』。"
            "格式如下，**严格遵守，不得省略**：\n\n"
            "【人物设定（必填，全集生效）】\n"
            "- {{char_name}}（{{role}}，UID #{{char_id}}）：\n"
            "  {{age}}岁，{{height}}，{{body}}，{{outfit_full}}，{{hair}}，{{eye_color}}，\n"
            "  画风：{{art_style}}\n"
            "  音色：{{voice_timbre}}（声音克隆 ID: {{voice_id}}）\n"
            "...\n\n"
            "【场景设定】\n"
            "- {{loc_name}}（{{loc_id}}）：\n"
            "  {{detailed_visual_description}}，整体色调：{{palette}}\n"
            "...\n\n"
            "【第 N 集分镜建议（小云雀会按这个走）】\n"
            "[场 1] {{scene_label}}\n"
            "  镜头 1（特写 3s）：{{action_zh}}\n"
            "  镜头 2（中景 4s）：{{action_zh}}\n"
            "  镜头 3（远景 3s）：{{action_zh}}\n"
            "  对白：{{dialogue}}\n"
            "  旁白：{{narration}}\n\n"
            "返回 JSON：{\"episode_id\":str,\"xyq_script\":str（上述完整 prompt 文本）,"
            "\"shots\":[{\"shot_id\":str,\"shot_type\":\"closeup|medium|wide|aerial\","
            "\"duration_s\":float,\"action\":str,\"emotion\":str,\"characters\":[str],"
            "\"location_id\":str,\"dialogue\":str,\"narration\":str}]}。"
        )
        user = json.dumps(
            {
                "episode_draft": episode_draft,
                "character_bibles": character_bibles,
                "scenes": scenes,
                "episode_seconds": episode_seconds,
                "genre": genre,
            },
            ensure_ascii=False,
        )
        return self._complete_json(
            sys_prompt, user, max_tokens=16000, label="format_for_xiaoyunque"
        )

    # ==================================================================
    # Generic completion entrypoint (for adapters/agents that hold a ref)
    # ==================================================================
    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        json_mode: bool = True,
        model: str | None = None,
        label: str = "complete",
    ) -> LLMResult:
        if json_mode:
            return self._complete_json(system, user, max_tokens=max_tokens, label=label, model=model)
        return self._complete_text(system, user, max_tokens=max_tokens, label=label, model=model)

    # ==================================================================
    # internals
    # ==================================================================
    def _complete_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int,
        label: str,
        model: str | None = None,
    ) -> LLMResult:
        raw = self._complete_text(
            system + "\n\n严格只返回 JSON，不要任何额外解释或代码块。",
            user,
            max_tokens=max_tokens,
            label=label,
            model=model,
        )
        if not raw.success:
            return raw
        text = raw.text.strip()
        # strip code fences
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
        try:
            raw.parsed = json.loads(text)
        except json.JSONDecodeError:
            # try to locate JSON braces
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    raw.parsed = json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    raw.parsed = None
                    raw.success = False
                    raw.error = "JSONDecodeError"
            else:
                raw.parsed = None
                raw.success = False
                raw.error = "JSONDecodeError"
        return raw

    def _complete_text(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int,
        label: str,
        model: str | None = None,
    ) -> LLMResult:
        if not self.available:
            return self._fallback(system, user, max_tokens=max_tokens, label=label)

        model_id = model or self._model
        headers = {
            "x-api-key": self._settings.anthropic_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        body = {
            "model": model_id,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }

        last_err: str | None = None
        for attempt in range(1, self._max_retries + 1):
            t0 = now_s()
            try:
                with httpx.Client(timeout=self._timeout_s) as client:
                    r = client.post(f"{API_BASE}/messages", headers=headers, json=body)
                dur = now_s() - t0
            except (httpx.HTTPError, OSError) as e:
                last_err = f"{type(e).__name__}: {e}"
                self._record_failure(label, model_id, last_err, attempt, dur=now_s() - t0)
                time.sleep(min(2 ** attempt, 30))
                continue

            if r.status_code != 200:
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                self._record_failure(label, model_id, last_err, attempt, dur=dur)
                if r.status_code in (429, 500, 502, 503, 504):
                    time.sleep(min(2 ** attempt, 30))
                    continue
                break

            try:
                data = r.json()
            except json.JSONDecodeError as e:
                last_err = f"non-json body: {e}"
                self._record_failure(label, model_id, last_err, attempt, dur=dur)
                break

            content = data.get("content") or []
            text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
            text = "\n".join(text_parts).strip()
            usage = data.get("usage") or {}
            in_tok = int(usage.get("input_tokens", 0))
            out_tok = int(usage.get("output_tokens", 0))
            rmb = self._cost.estimate_llm("anthropic", in_tok, out_tok)
            self._cost.record(
                CostEntry(
                    timestamp_s=time.time(),
                    provider="anthropic",
                    operation=f"llm.{label}",
                    model=model_id,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    duration_s=dur,
                    rmb=rmb,
                    success=True,
                    extra={"attempt": attempt},
                )
            )
            return LLMResult(
                text=text,
                parsed=None,
                model=model_id,
                input_tokens=in_tok,
                output_tokens=out_tok,
                latency_s=dur,
            )

        # all retries failed → fallback
        if self.mock_fallback is not None:
            try:
                return self._fallback(system, user, max_tokens=max_tokens, label=label, err=last_err)
            except Exception:  # noqa: BLE001
                pass
        return LLMResult(
            text="",
            parsed=None,
            model=model_id,
            input_tokens=0,
            output_tokens=0,
            latency_s=0.0,
            success=False,
            error=last_err,
        )

    def _record_failure(
        self,
        label: str,
        model: str,
        err: str,
        attempt: int,
        *,
        dur: float,
    ) -> None:
        self._cost.record(
            CostEntry(
                timestamp_s=time.time(),
                provider="anthropic",
                operation=f"llm.{label}",
                model=model,
                duration_s=dur,
                success=False,
                error_class=err.split(":", 1)[0],
                extra={"attempt": attempt, "err": err[:200]},
            )
        )

    def _fallback(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int,
        label: str,
        err: str | None = None,
    ) -> LLMResult:
        if self.mock_fallback is None:
            return LLMResult(
                text="",
                parsed=None,
                model=self._model,
                input_tokens=0,
                output_tokens=0,
                latency_s=0.0,
                provider="anthropic-degraded",
                success=False,
                error=err or "anthropic unavailable",
            )
        # Try the shared RealLLMAdapter / MockLLMAdapter generic complete().
        if hasattr(self.mock_fallback, "complete"):
            r = self.mock_fallback.complete(
                system=system, user=user, max_tokens=max_tokens, label=label
            )
            return LLMResult(
                text=getattr(r, "text", ""),
                parsed=getattr(r, "parsed", None),
                model=getattr(r, "model", "fallback"),
                input_tokens=getattr(r, "input_tokens", 0),
                output_tokens=getattr(r, "output_tokens", 0),
                latency_s=getattr(r, "latency_s", 0.0),
                provider="anthropic-fallback",
                success=getattr(r, "success", True),
                error=getattr(r, "error", None),
            )
        # No shared interface — return empty success so downstream agents
        # can still build a stub blueprint.
        return LLMResult(
            text="{}",
            parsed={},
            model=self._model,
            input_tokens=0,
            output_tokens=0,
            latency_s=0.0,
            provider="anthropic-degraded",
            success=True,
        )
