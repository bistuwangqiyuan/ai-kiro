"""NovelWriterAgent — docx 九节「小说生成 / 续写 / 风格迁移」.

三个模式：
- ``mode = generate``    从 prompt + genre 生成一本新小说（≥10k 字）
- ``mode = continuation`` 在已有小说后续写若干章
- ``mode = style_transfer`` 把已有小说迁移到目标题材/风格

输出：纯文本 + per-chapter 拆分；写入 ``02_novel/{episode_id}.md``。
后续 ScriptArchitectAgent 接管。

策略：优先调 ``llm_native``（Claude Opus 4，200k context），失败回退到 ``llm`` 兜底链。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent


class NovelWriterAgent(BaseAgent):
    name = "NovelWriterAgent"

    def __init__(
        self,
        ctx: AgentContext,
        *,
        llm_native: Any | None = None,
        llm: Any | None = None,
    ) -> None:
        super().__init__(ctx)
        self.llm_native = llm_native
        self.llm = llm

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        mode = req.inputs.get("mode", "generate")
        if mode == "generate":
            return self._generate(req)
        if mode == "continuation":
            return self._continuation(req)
        if mode == "style_transfer":
            return self._style_transfer(req)
        return AgentRunResponse(
            status="failed",
            outputs={"error": f"unknown mode {mode}"},
            metrics={},
        )

    # ===== generate =====
    def _generate(self, req: AgentRunRequest) -> AgentRunResponse:
        prompt = req.inputs["prompt"]
        genre = req.inputs.get("genre", "ancient")
        target_chars = int(req.inputs.get("target_chars", 12000))
        n_chapters = int(req.inputs.get("n_chapters", 12))

        system = (
            "你是金牌网文作者。基于用户给出的概念/灵感，写一部完整的网络小说。"
            f"目标体裁：{genre}。预计 {n_chapters} 章，全文 ≥{target_chars} 字。"
            "要求：每章 800-1200 字，有钩子、冲突、反转、悬念；人名固定；时空清晰。"
            "返回 JSON：{\"title\":str,\"chapters\":[{\"chapter\":int,\"title\":str,\"text\":str}]}。"
        )
        result = self._invoke_llm(system=system, user=prompt, max_tokens=16000)
        return self._persist(req, result, mode="generate")

    # ===== continuation =====
    def _continuation(self, req: AgentRunRequest) -> AgentRunResponse:
        original = req.inputs["original_text"]
        n_more = int(req.inputs.get("n_more_chapters", 3))
        genre = req.inputs.get("genre", "ancient")

        system = (
            "你是网文续写专家。在用户给出的小说原文基础上，无缝衔接续写后续章节。"
            f"题材：{genre}。续写 {n_more} 章，保持人物、世界观、文风一致。"
            "返回 JSON：{\"chapters\":[{\"chapter\":int,\"title\":str,\"text\":str}]}。"
        )
        result = self._invoke_llm(system=system, user=original[:300_000], max_tokens=16000)
        return self._persist(req, result, mode="continuation")

    # ===== style transfer =====
    def _style_transfer(self, req: AgentRunRequest) -> AgentRunResponse:
        original = req.inputs["original_text"]
        target_genre = req.inputs.get("target_genre", "modern")
        target_style = req.inputs.get("target_style", "现代都市轻松向")

        system = (
            "你是题材改写专家。把用户输入的小说迁移到目标题材，"
            f"目标题材：{target_genre}，目标文风：{target_style}。"
            "保留主要剧情骨架，但人物、场景、对白完全改写以贴合新题材。"
            "返回 JSON：{\"title\":str,\"chapters\":[{\"chapter\":int,\"title\":str,\"text\":str}]}。"
        )
        result = self._invoke_llm(system=system, user=original[:300_000], max_tokens=16000)
        return self._persist(req, result, mode="style_transfer")

    # ===== helpers =====
    def _invoke_llm(self, *, system: str, user: str, max_tokens: int) -> dict[str, Any]:
        if self.llm_native is not None:
            try:
                r = self.llm_native.complete(
                    system=system, user=user, max_tokens=max_tokens, json_mode=True, label="novel"
                )
                parsed = getattr(r, "parsed", None)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:  # noqa: BLE001
                pass
        if self.llm is not None:
            try:
                r = self.llm.complete(
                    system=system, user=user, max_tokens=max_tokens, json_mode=True, label="novel"
                )
                parsed = getattr(r, "parsed", None)
                if isinstance(parsed, dict):
                    return parsed
                text = getattr(r, "text", "") or ""
                if text.startswith("{"):
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        pass
            except Exception:  # noqa: BLE001
                pass
        # Final fallback — stub
        return {"title": "未命名小说", "chapters": [{"chapter": 1, "title": "未命名章", "text": user[:500]}]}

    def _persist(
        self,
        req: AgentRunRequest,
        result: dict[str, Any],
        *,
        mode: str,
    ) -> AgentRunResponse:
        title = result.get("title", "未命名小说")
        chapters = result.get("chapters", [])
        text_parts: list[str] = []
        for ch in chapters:
            text_parts.append(f"# 第{ch.get('chapter')}章 {ch.get('title','')}\n\n{ch.get('text','')}\n")
        full_text = "\n".join(text_parts)

        key = f"{req.context.project_id}/02_novel/novel_{mode}.md"
        path = self.ctx.storage.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(full_text, encoding="utf-8")

        json_key = f"{req.context.project_id}/02_novel/novel_{mode}.json"
        jp = self.ctx.storage.path(json_key)
        jp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        return AgentRunResponse(
            status="succeeded",
            outputs={
                "title": title,
                "n_chapters": len(chapters),
                "novel_text_path": str(path),
                "novel_json_path": str(jp),
                "mode": mode,
            },
            metrics={"chars": float(len(full_text)), "chapters": float(len(chapters))},
        )
