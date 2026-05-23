"""CopyGeneratorAgent — 标题 / 简介 / tags / 引流文案（docx 八节「文案配套」）.

按 3 平台规格分别产出（长度上限不同）：
- douyin: 标题 ≤55 / 简介 ≤1000 / tags ≤6
- kuaishou: 标题 ≤50 / 简介 ≤500 / tags ≤8
- weixin: 标题 ≤22 / 简介 ≤600 / tags ≤3

策略：
- 有 LLM（Claude Opus / Doubao）→ 调它产高质量爆款文案；
- 无 LLM → 用 template + 题材关键词拼接兜底。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent
from manhuaju.utils.paths import config_dir


class CopyGeneratorAgent(BaseAgent):
    name = "CopyGeneratorAgent"

    def __init__(self, ctx: AgentContext, *, llm: Any | None = None) -> None:
        super().__init__(ctx)
        self.llm = llm
        self._platforms = _load_platform_specs()

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        episode_id = req.inputs["episode_id"]
        title_hint = req.inputs.get("title", "未定")
        synopsis = req.inputs.get("synopsis", "")
        genre = req.inputs.get("genre", "ancient")
        characters = req.inputs.get("characters", []) or []
        emotion = req.inputs.get("emotion", "neutral")
        platforms: list[str] = req.inputs.get(
            "platforms", ["douyin", "kuaishou", "weixin"]
        )

        copies: dict[str, dict[str, Any]] = {}
        llm_used = False
        for plat in platforms:
            spec = self._platforms.get(plat, {})
            copy = self._build_copy(
                platform=plat,
                spec=spec,
                episode_id=episode_id,
                title_hint=title_hint,
                synopsis=synopsis,
                genre=genre,
                characters=characters,
                emotion=emotion,
            )
            llm_used = llm_used or copy.get("source") == "llm"
            copies[plat] = copy

        # Persist
        manifest = self.ctx.storage.path(
            f"{req.context.project_id}/08_covers/{episode_id}_copy.json"
        )
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(copies, ensure_ascii=False, indent=2), encoding="utf-8")

        return AgentRunResponse(
            status="succeeded",
            outputs={"copies": copies, "manifest_path": str(manifest)},
            metrics={"platforms": float(len(copies)), "llm_used": 1.0 if llm_used else 0.0},
        )

    # ----- builder -----
    def _build_copy(
        self,
        *,
        platform: str,
        spec: dict[str, Any],
        episode_id: str,
        title_hint: str,
        synopsis: str,
        genre: str,
        characters: list[dict[str, Any]],
        emotion: str,
    ) -> dict[str, Any]:
        title_max = int(spec.get("title_max_chars", 50))
        intro_max = int(spec.get("intro_max_chars", 500))
        tags_max = int(spec.get("tags_max", 6))

        if self.llm is not None:
            try:
                return self._llm_copy(
                    platform=platform,
                    episode_id=episode_id,
                    title_hint=title_hint,
                    synopsis=synopsis,
                    genre=genre,
                    characters=characters,
                    emotion=emotion,
                    title_max=title_max,
                    intro_max=intro_max,
                    tags_max=tags_max,
                )
            except Exception:  # noqa: BLE001
                pass
        return self._template_copy(
            platform=platform,
            episode_id=episode_id,
            title_hint=title_hint,
            synopsis=synopsis,
            genre=genre,
            characters=characters,
            emotion=emotion,
            title_max=title_max,
            intro_max=intro_max,
            tags_max=tags_max,
        )

    def _llm_copy(self, **kw: Any) -> dict[str, Any]:
        system = (
            "你是漫剧短视频运营专家。根据剧情产出爆款文案。"
            "输出 JSON：{\"title\":str（≤N1字）,\"intro\":str（≤N2字）,"
            "\"tags\":[str]（≤N3个，每个2-6字），\"hooks\":[str]（3条1-2句钩子文案）}。"
        )
        user = (
            f"平台：{kw['platform']}\n"
            f"标题字数上限：{kw['title_max']}；简介上限：{kw['intro_max']}；tags 上限：{kw['tags_max']}\n"
            f"集 ID：{kw['episode_id']}\n"
            f"题材：{kw['genre']}\n"
            f"主要角色：{', '.join(c.get('name', c.get('char_id', '')) for c in kw['characters'][:5])}\n"
            f"情绪基调：{kw['emotion']}\n"
            f"剧情简介：{kw['synopsis'][:1200]}\n"
            f"标题参考：{kw['title_hint']}"
        )
        out = None
        if hasattr(self.llm, "complete"):
            r = self.llm.complete(system=system, user=user, max_tokens=512, json_mode=True, label="copy")
            out = getattr(r, "parsed", None) or _safe_json(getattr(r, "text", ""))
        if not isinstance(out, dict):
            raise RuntimeError("llm copy: empty")
        return {
            "title": _truncate(out.get("title", ""), kw["title_max"]),
            "intro": _truncate(out.get("intro", ""), kw["intro_max"]),
            "tags": [_truncate(t, 8) for t in (out.get("tags") or [])[: kw["tags_max"]]],
            "hooks": (out.get("hooks") or [])[:3],
            "source": "llm",
        }

    def _template_copy(self, **kw: Any) -> dict[str, Any]:
        title = kw["title_hint"]
        if not title or title == "未定":
            char = (kw["characters"][0].get("name") if kw["characters"] else "她") or "她"
            title = f"{char}的{kw['genre']}传奇·第{kw['episode_id'].lstrip('ep')}集"
        intro = (
            (kw["synopsis"] or "命运转折，情深难忘。") + "\n\n#漫剧 #" + kw["genre"]
        )
        tag_pool_zh = {
            "ancient": ["古风漫剧", "宫斗", "权谋", "情劫", "玄机"],
            "modern": ["都市漫剧", "霸总", "暧昧", "高燃", "反转"],
            "sweet_pet": ["甜宠", "心动", "高甜", "撒糖", "宠妻"],
            "suspense": ["悬疑", "反转", "烧脑", "推理", "惊悚"],
            "xuanhuan": ["玄幻", "修仙", "热血", "封神", "天劫"],
            "xianxia": ["仙侠", "御剑", "情劫", "渡劫", "天命"],
            "campus": ["校园", "青春", "初恋", "高甜", "回忆"],
            "urban": ["都市", "职场", "成长", "逆袭", "情感"],
        }.get(kw["genre"], ["漫剧", "AI 动画"])
        return {
            "title": _truncate(title, kw["title_max"]),
            "intro": _truncate(intro, kw["intro_max"]),
            "tags": tag_pool_zh[: kw["tags_max"]],
            "hooks": [
                f"她以为这一切只是开始……",
                f"直到{kw['emotion']}的那一刻，命运彻底翻转！",
                f"第{kw['episode_id'].lstrip('ep')}集 · 你不会想错过的反转！",
            ],
            "source": "template",
        }


# ----- helpers -----
def _load_platform_specs() -> dict[str, dict[str, Any]]:
    path = config_dir() / "distribution-platforms.yaml"
    if not path.exists():
        return {}
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cfg.get("platforms", {}) or {}
    except yaml.YAMLError:
        return {}


def _safe_json(text: str) -> Any:
    text = (text or "").strip()
    if not text:
        return {}
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s = text.find("{")
        e = text.rfind("}")
        if s >= 0 and e > s:
            try:
                return json.loads(text[s : e + 1])
            except json.JSONDecodeError:
                return {}
    return {}


def _truncate(text: str, n: int) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1] + "…"
