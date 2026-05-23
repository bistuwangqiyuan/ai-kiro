"""XYQTemplateFormatterAgent — 跨集一致性「防线 1」编剧层强约束 ★.

tech.md 第三节关键创新：
> 每一集的剧本都要重复『人物设定块』和『场景设定块』。
> 这是逆向调试出来的，小云雀的档案系统跨集容易丢失。

本 Agent 在 ScriptWriter / Storyboard 之后、RenderOrchestrator 之前运行，
把每集的剧本前缀填充完整的人物设定 + 场景设定 + 分镜建议，输出
``xyq_script`` 文本（直接喂给 ``RealXiaoyunqueAdapter`` 的 prompt 字段）。

策略：
- 若注入 ``llm_native``（Claude Opus / Anthropic adapter）→ 调它的
  ``format_for_xiaoyunque`` 高质量改写；
- 否则用本地 deterministic template（含 bible / scene meta），保证 schema 不变。
"""

from __future__ import annotations

from typing import Any

from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent


class XYQTemplateFormatterAgent(BaseAgent):
    name = "XYQTemplateFormatterAgent"

    def __init__(self, ctx: AgentContext, *, llm_native: Any | None = None) -> None:
        super().__init__(ctx)
        self.llm_native = llm_native

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        episode = req.inputs["episode"]
        script = req.inputs["script"]
        storyboard = req.inputs.get("storyboard", {})
        bibles: list[dict[str, Any]] = req.inputs.get("bibles", [])
        scenes: list[dict[str, Any]] = req.inputs.get("scenes", [])
        genre = req.inputs.get("genre", "ancient")
        style_prompt = req.inputs.get("style_prompt", "")
        episode_seconds = int(req.inputs.get("episode_seconds", 75))

        xyq_text = self._compose(
            episode=episode,
            script=script,
            storyboard=storyboard,
            bibles=bibles,
            scenes=scenes,
            genre=genre,
            style_prompt=style_prompt,
            episode_seconds=episode_seconds,
        )

        # 持久化
        ep_id = episode.get("episode_id", "ep01")
        key = f"{req.context.project_id}/05_scripts/{ep_id}_xyq.txt"
        path = self.ctx.storage.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(xyq_text, encoding="utf-8")

        return AgentRunResponse(
            status="succeeded",
            outputs={
                "xyq_script": xyq_text,
                "xyq_script_path": str(path),
                "characters_block_chars": _count_chars(xyq_text, marker="【人物设定"),
                "scenes_block_chars": _count_chars(xyq_text, marker="【场景设定"),
            },
            metrics={"xyq_chars": float(len(xyq_text))},
        )

    # ----- composition -----
    def _compose(
        self,
        *,
        episode: dict[str, Any],
        script: dict[str, Any],
        storyboard: dict[str, Any],
        bibles: list[dict[str, Any]],
        scenes: list[dict[str, Any]],
        genre: str,
        style_prompt: str,
        episode_seconds: int,
    ) -> str:
        if self.llm_native is not None and hasattr(self.llm_native, "format_for_xiaoyunque"):
            try:
                res = self.llm_native.format_for_xiaoyunque(
                    episode_draft={
                        "episode_id": episode.get("episode_id"),
                        "title": episode.get("title"),
                        "script": script,
                        "storyboard": storyboard,
                    },
                    character_bibles=bibles,
                    scenes=scenes,
                    episode_seconds=episode_seconds,
                    genre=genre,
                )
                parsed = getattr(res, "parsed", None) or {}
                if isinstance(parsed, dict) and parsed.get("xyq_script"):
                    return str(parsed["xyq_script"])
                if getattr(res, "text", None):
                    return str(res.text)
            except Exception:  # noqa: BLE001
                pass
        return self._template_compose(
            episode=episode,
            script=script,
            storyboard=storyboard,
            bibles=bibles,
            scenes=scenes,
            genre=genre,
            style_prompt=style_prompt,
            episode_seconds=episode_seconds,
        )

    def _template_compose(
        self,
        *,
        episode: dict[str, Any],
        script: dict[str, Any],
        storyboard: dict[str, Any],
        bibles: list[dict[str, Any]],
        scenes: list[dict[str, Any]],
        genre: str,
        style_prompt: str,
        episode_seconds: int,
    ) -> str:
        ep_id = episode.get("episode_id", "ep01")
        title = episode.get("title", "")
        lines: list[str] = []
        lines.append(f"# {ep_id} · {title}")
        lines.append(f"题材：{genre}    时长：{episode_seconds} 秒    画风：{style_prompt}")
        lines.append("")
        # 1. 人物设定块（防线 1）
        lines.append("【人物设定（必填，全集生效）】")
        for b in bibles:
            char_id = b.get("char_id", "")
            name = b.get("display_name") or b.get("name") or char_id
            role = b.get("role", "")
            ap = b.get("appearance", {}) or {}
            outfit = (b.get("outfit_library") or [{}])[0]
            voice = b.get("voice_profile", {}) or {}
            lines.append(
                f"- {name}（{role}，UID #{char_id}）："
            )
            lines.append(
                f"  {ap.get('age', '青年')}，{ap.get('height', '中等')}，"
                f"{ap.get('body', '匀称')}，{outfit.get('description', '默认服饰')}，"
                f"{ap.get('hair', '黑发')}，{ap.get('eye_color', '深邃')}"
            )
            lines.append(f"  画风：{style_prompt}")
            lines.append(
                f"  音色：{voice.get('timbre', '中性')}（声音克隆 ID: "
                f"{voice.get('voice_id', f'voice_{char_id}_v1')}）"
            )
        lines.append("")
        # 2. 场景设定块
        lines.append("【场景设定】")
        for sc in scenes:
            loc_id = sc.get("location_id") or sc.get("id") or "loc"
            name = sc.get("name", loc_id)
            atmosphere = sc.get("atmosphere", "")
            palette = sc.get("palette", "")
            lines.append(f"- {name}（{loc_id}）：{atmosphere}，整体色调：{palette}")
        lines.append("")
        # 3. 分镜建议
        lines.append(f"【{ep_id} 分镜建议（小云雀按这个走）】")
        shots = storyboard.get("shots", []) or []
        for i, shot in enumerate(shots, start=1):
            shot_type = shot.get("shot_type", "medium")
            dur = shot.get("target_seconds") or shot.get("duration_s") or 3
            mood = shot.get("mood", "neutral")
            key_action = shot.get("key_action") or shot.get("action") or ""
            loc = shot.get("location_id") or shot.get("scene_id") or ""
            lines.append(
                f"[镜头 {i}]（{shot_type} {dur}s，{loc}，{mood}）{key_action}"
            )
            for d in shot.get("dialogue_lines", []) or []:
                spk = d.get("speaker", "")
                txt = d.get("text", "")
                if txt:
                    lines.append(f"  对白({spk})：{txt}")
            narr = shot.get("narration") or {}
            if isinstance(narr, dict) and narr.get("text"):
                lines.append(f"  旁白：{narr['text']}")
        lines.append("")
        lines.append("# 输出要求：保持角色脸部、发型、服饰跨镜完全一致；")
        lines.append("# 不要叠加文字字幕；运镜遵守 180 度规则；不要崩坏。")
        return "\n".join(lines)


def _count_chars(text: str, *, marker: str) -> int:
    start = text.find(marker)
    if start < 0:
        return 0
    end = text.find("\n\n", start)
    if end < 0:
        return len(text) - start
    return end - start
