"""Real LLM adapter — OpenAI-compatible multi-provider with auto-fallback.

Design pattern: **Real-augmented Mock**. We use the deterministic
`MockLLMAdapter` as a *schema scaffold* and call the real LLM to enrich
user-visible text fields (synopsis, logline, dialogue, scene description).

This guarantees:

1. Schema compliance — pipeline never breaks on a malformed live response.
2. Cost-bounded — only short, focused completions hit the wire.
3. Determinism for non-Live runs — Mock path remains pure.
4. Graceful degradation — provider 5xx / 4xx → next provider → mock.

The adapter exposes the **exact** method signatures of `MockLLMAdapter` so it
is a drop-in replacement via `AdapterFactory`.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx

from manhuaju.adapters.llm.mock_llm_adapter import MockLLMAdapter
from manhuaju.core.cost_tracker import CostEntry, CostTracker, now_s
from manhuaju.core.provider_settings import ProviderEndpoint, ProviderSettings


class _AllProvidersFailed(RuntimeError):
    pass


class RealLLMAdapter:
    name = "RealLLMAdapter"

    def __init__(
        self,
        *,
        settings: ProviderSettings,
        cost: CostTracker,
        config: dict[str, Any] | None = None,
        mock_fallback: MockLLMAdapter | None = None,
    ) -> None:
        self._settings = settings
        self._cost = cost
        self._cfg = config or {}
        self._mock_scaffold = MockLLMAdapter()
        self._mock_fallback = mock_fallback
        self._timeout = float(self._cfg.get("request_timeout_s", 60))
        self._max_retries = int(self._cfg.get("max_retries", 2))
        self._enabled_provider_names = set(
            self._cfg.get("providers", [e.name for e in self._settings.llm_endpoints])
        )

    # ---------------- public API (mirrors MockLLMAdapter) ----------------

    def story_blueprint(self, *, novel_text: str, project_id: str, seed: int) -> dict[str, Any]:
        scaffold = self._mock_scaffold.story_blueprint(
            novel_text=novel_text, project_id=project_id, seed=seed
        )
        prompt = self._prompt_blueprint(novel_text)
        enriched = self._call_json(prompt, op="llm.story_blueprint", max_tokens=900)
        if enriched:
            scaffold = _merge_blueprint(scaffold, enriched)
        return scaffold

    def episode_plan(
        self, *, blueprint: dict[str, Any], episode_count: int, seed: int
    ) -> dict[str, Any]:
        scaffold = self._mock_scaffold.episode_plan(
            blueprint=blueprint, episode_count=episode_count, seed=seed
        )
        prompt = self._prompt_episode_plan(blueprint, episode_count)
        enriched = self._call_json(prompt, op="llm.episode_plan", max_tokens=1200)
        if enriched and "episodes" in enriched and isinstance(enriched["episodes"], list):
            for i, ep in enumerate(scaffold.get("episodes", [])):
                if i < len(enriched["episodes"]):
                    src = enriched["episodes"][i]
                    if isinstance(src, dict):
                        for k in ("title", "synopsis", "hook", "twist", "cliffhanger"):
                            if v := src.get(k):
                                ep[k] = v
        return scaffold

    def character_bible(
        self, *, character_stub: dict[str, Any], blueprint: dict[str, Any], seed: int
    ) -> dict[str, Any]:
        scaffold = self._mock_scaffold.character_bible(
            character_stub=character_stub, blueprint=blueprint, seed=seed
        )
        prompt = self._prompt_character_bible(character_stub, blueprint)
        enriched = self._call_json(prompt, op="llm.character_bible", max_tokens=600)
        if enriched:
            for k in ("personality", "backstory", "dialect", "voice_keywords", "appearance_notes"):
                if v := enriched.get(k):
                    scaffold[k] = v
        return scaffold

    def style_lock(
        self, *, project_id: str, blueprint: dict[str, Any], config: dict[str, Any]
    ) -> dict[str, Any]:
        # Style is deterministic by design — no LLM call needed.
        return self._mock_scaffold.style_lock(
            project_id=project_id, blueprint=blueprint, config=config
        )

    def write_script(
        self, *, episode: dict[str, Any], characters: list[dict[str, Any]], seed: int
    ) -> dict[str, Any]:
        scaffold = self._mock_scaffold.write_script(
            episode=episode, characters=characters, seed=seed
        )
        prompt = self._prompt_script(episode, characters)
        enriched = self._call_json(prompt, op="llm.write_script", max_tokens=2000)
        if enriched:
            self._merge_script(scaffold, enriched)
        return scaffold

    def storyboard(self, *, script: dict[str, Any], style_sha: str, seed: int) -> dict[str, Any]:
        scaffold = self._mock_scaffold.storyboard(script=script, style_sha=style_sha, seed=seed)
        prompt = self._prompt_storyboard(script)
        enriched = self._call_json(prompt, op="llm.storyboard", max_tokens=1800)
        if enriched and isinstance(enriched.get("shots"), list):
            for i, shot in enumerate(scaffold.get("shots", [])):
                if i < len(enriched["shots"]):
                    src = enriched["shots"][i]
                    if isinstance(src, dict):
                        for k in ("camera_angle", "camera_motion", "lighting", "composition_notes"):
                            if v := src.get(k):
                                shot[k] = v
        return scaffold

    # ---------------- low-level: raw chat completion ----------------

    def chat(
        self,
        *,
        messages: list[dict[str, str]],
        op: str,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        json_mode: bool = True,
    ) -> str | None:
        """Public escape hatch for non-scaffolded callers (moderation, QA proxy).

        Returns the raw assistant text, or `None` if all providers failed.
        """
        for ep in self._eligible_endpoints():
            text = self._call_one(
                ep,
                messages=messages,
                op=op,
                max_tokens=max_tokens,
                temperature=temperature,
                json_mode=json_mode,
            )
            if text is not None:
                return text
        return None

    # ---------------- internals ----------------

    def _eligible_endpoints(self) -> list[ProviderEndpoint]:
        return [
            e
            for e in self._settings.llm_endpoints
            if e.enabled and e.api_key and e.name in self._enabled_provider_names
        ]

    def _call_json(
        self, prompt: str, *, op: str, max_tokens: int = 800
    ) -> dict[str, Any] | None:
        text = self.chat(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a JSON-only response generator for a video production "
                        "pipeline. Output a single valid JSON object. Never include "
                        "Markdown fences or commentary."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            op=op,
            max_tokens=max_tokens,
            temperature=0.6,
            json_mode=True,
        )
        if text is None:
            return None
        return _parse_json(text)

    def _call_one(
        self,
        ep: ProviderEndpoint,
        *,
        messages: list[dict[str, str]],
        op: str,
        max_tokens: int,
        temperature: float,
        json_mode: bool,
    ) -> str | None:
        url = f"{ep.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {ep.api_key}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {
            "model": ep.default_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        if json_mode and ep.json_mode:
            body["response_format"] = {"type": "json_object"}

        last_err: Exception | None = None
        for attempt in range(self._max_retries + 1):
            t0 = now_s()
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    r = client.post(url, headers=headers, json=body)
                duration = now_s() - t0
                if r.status_code == 200:
                    data = r.json()
                    text, in_tok, out_tok = _extract_completion(data)
                    rmb = self._cost.estimate_llm(ep.name, in_tok, out_tok)
                    self._cost.record(
                        CostEntry(
                            timestamp_s=time.time(),
                            provider=ep.name,
                            operation=op,
                            model=ep.default_model,
                            input_tokens=in_tok,
                            output_tokens=out_tok,
                            duration_s=duration,
                            rmb=rmb,
                            success=True,
                        )
                    )
                    return text
                # 4xx / 5xx — record + try next attempt or next provider
                err = f"HTTP {r.status_code}"
                last_err = RuntimeError(err)
                self._cost.record(
                    CostEntry(
                        timestamp_s=time.time(),
                        provider=ep.name,
                        operation=op,
                        model=ep.default_model,
                        duration_s=duration,
                        success=False,
                        error_class=err,
                        extra={"body": r.text[:200]},
                    )
                )
                # 4xx (except 408/429) → likely permanent → don't retry on this provider.
                if 400 <= r.status_code < 500 and r.status_code not in (408, 429):
                    return None
            except (httpx.HTTPError, OSError) as e:
                last_err = e
                duration = now_s() - t0
                self._cost.record(
                    CostEntry(
                        timestamp_s=time.time(),
                        provider=ep.name,
                        operation=op,
                        model=ep.default_model,
                        duration_s=duration,
                        success=False,
                        error_class=type(e).__name__,
                    )
                )
            time.sleep(min(2 ** attempt, 4))
        if last_err:
            return None
        return None

    # ---------------- prompts ----------------

    @staticmethod
    def _prompt_blueprint(novel_text: str) -> str:
        return (
            "You are the StoryArchitect for an AI-driven manga drama production. "
            "Read the novel snippet below and return JSON:\n"
            '{"logline": str, "tone": str, "themes": [str], "synopsis_3_acts": str}\n\n'
            "Snippet (truncated to 4k chars):\n"
            f"{novel_text[:4000]}"
        )

    @staticmethod
    def _prompt_episode_plan(bp: dict[str, Any], n: int) -> str:
        return (
            "You are the EpisodePlanner. Based on the StoryBlueprint below, "
            f"split the story into exactly {n} episodes. Return JSON:\n"
            '{"episodes": [{"title": str, "synopsis": str, "hook": str, "twist": str, '
            '"cliffhanger": str}]}\n\n'
            f"Blueprint:\n{json.dumps(bp, ensure_ascii=False)[:3000]}"
        )

    @staticmethod
    def _prompt_character_bible(stub: dict[str, Any], bp: dict[str, Any]) -> str:
        return (
            "You are the CharacterBible writer. Enrich this character stub for visual "
            "consistency across episodes. Return JSON:\n"
            '{"personality": str, "backstory": str, "dialect": str, '
            '"voice_keywords": [str], "appearance_notes": str}\n\n'
            f"Stub: {json.dumps(stub, ensure_ascii=False)[:1500]}\n"
            f"World tone: {(bp.get('tone') or '')[:200]}"
        )

    @staticmethod
    def _prompt_script(ep: dict[str, Any], chars: list[dict[str, Any]]) -> str:
        char_brief = ", ".join(
            f"{c.get('name', 'unknown')}({c.get('archetype', '?')})" for c in chars[:5]
        )
        return (
            "You are the ScriptWriter for an AI manga drama. Write 3 short scenes "
            "for the episode below. Each scene has 2 dialogues. Return JSON:\n"
            '{"scenes":[{"scene_id": str, "description": str, '
            '"dialogues":[{"character": str, "text": str}]}]}\n\n'
            f"Episode: {json.dumps(ep, ensure_ascii=False)[:1500]}\n"
            f"Cast: {char_brief}"
        )

    @staticmethod
    def _prompt_storyboard(script: dict[str, Any]) -> str:
        return (
            "You are the StoryboardDirector. For each shot in the script, suggest "
            "camera_angle / camera_motion / lighting / composition_notes. Return JSON:\n"
            '{"shots": [{"camera_angle": str, "camera_motion": str, "lighting": str, '
            '"composition_notes": str}]}\n\n'
            f"Script: {json.dumps(script, ensure_ascii=False)[:2000]}"
        )

    # ---------------- merging ----------------

    @staticmethod
    def _merge_script(scaffold: dict[str, Any], enriched: dict[str, Any]) -> None:
        if not isinstance(enriched.get("scenes"), list):
            return
        for i, scene in enumerate(scaffold.get("scenes", [])):
            if i >= len(enriched["scenes"]):
                break
            src = enriched["scenes"][i]
            if not isinstance(src, dict):
                continue
            if v := src.get("description"):
                scene["description"] = v
            if isinstance(src.get("dialogues"), list):
                for j, d in enumerate(scene.get("dialogues", [])):
                    if j < len(src["dialogues"]):
                        sd = src["dialogues"][j]
                        if isinstance(sd, dict) and (text := sd.get("text")):
                            d["text"] = text


def _parse_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    # Strip Markdown fences if model ignored instructions.
    if text.startswith("```"):
        parts = text.split("```", 2)
        if len(parts) >= 2:
            inner = parts[1]
            if inner.lower().startswith("json"):
                inner = inner[4:]
            text = inner.strip()
    try:
        out = json.loads(text)
        return out if isinstance(out, dict) else None
    except (json.JSONDecodeError, ValueError):
        # Try to recover the first {...} block.
        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            try:
                out = json.loads(text[first : last + 1])
                return out if isinstance(out, dict) else None
            except (json.JSONDecodeError, ValueError):
                return None
    return None


def _extract_completion(data: dict[str, Any]) -> tuple[str, int, int]:
    choices = data.get("choices") or []
    text = ""
    if choices and isinstance(choices[0], dict):
        msg = choices[0].get("message") or {}
        text = str(msg.get("content") or "")
    usage = data.get("usage") or {}
    in_tok = int(usage.get("prompt_tokens", 0) or 0)
    out_tok = int(usage.get("completion_tokens", 0) or 0)
    return text, in_tok, out_tok


def _merge_blueprint(scaffold: dict[str, Any], enriched: dict[str, Any]) -> dict[str, Any]:
    for k in ("logline", "tone", "synopsis_3_acts", "synopsis"):
        if v := enriched.get(k):
            scaffold[k] = v
    if isinstance(enriched.get("themes"), list) and enriched["themes"]:
        scaffold["themes"] = [str(t) for t in enriched["themes"][:5]]
    return scaffold
