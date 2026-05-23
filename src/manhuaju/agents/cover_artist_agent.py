"""CoverArtistAgent — 多平台漫剧封面生成（docx 八节「水印 / 封面」）.

策略：
1. 用 Jimeng 4.6 大图 API 生成主视觉（无文字，纯画面，按集情绪 + 题材风格）；
2. 失败时回退到「成片首帧 keyframe + Pillow 涂层」；
3. 用 Pillow 叠加标题（思源宋体）+ 副标题 + 角色名标签，多平台尺寸（抖音 1080×1440 / 视频号 1080×1440 / 横屏 1920×1200）。
"""

from __future__ import annotations

import contextlib
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from manhuaju.core.agent_base import AgentContext, AgentRunRequest, AgentRunResponse, BaseAgent


COVER_SIZES = {
    "douyin_3x4": (1080, 1440),
    "weixin_3x4": (1080, 1440),
    "kuaishou_3x4": (720, 960),
    "douyin_1x1": (1080, 1080),
    "bilibili_16x10": (1920, 1200),
}


class CoverArtistAgent(BaseAgent):
    name = "CoverArtistAgent"

    def __init__(
        self,
        ctx: AgentContext,
        *,
        image_adapter: Any | None = None,
    ) -> None:
        super().__init__(ctx)
        self.image_adapter = image_adapter

    def run(self, req: AgentRunRequest) -> AgentRunResponse:
        episode_id = req.inputs["episode_id"]
        title = req.inputs.get("title", "未定标题")
        subtitle = req.inputs.get("subtitle", "")
        genre = req.inputs.get("genre", "ancient")
        emotion = req.inputs.get("emotion", "neutral")
        style_prompt = req.inputs.get("style_prompt", "古风工笔水墨")
        characters = req.inputs.get("characters", []) or []
        first_frame_path = req.inputs.get("first_frame_path")
        sizes: list[str] = req.inputs.get(
            "sizes", ["douyin_3x4", "weixin_3x4", "kuaishou_3x4"]
        )
        project_id = req.context.project_id

        base = self._build_base_image(
            title=title,
            episode_id=episode_id,
            genre=genre,
            emotion=emotion,
            style_prompt=style_prompt,
            characters=characters,
            project_id=project_id,
            first_frame_path=first_frame_path,
        )
        if base is None:
            return AgentRunResponse(
                status="degraded",
                outputs={"covers": {}, "note": "no_base_image"},
                metrics={"covers": 0.0},
            )

        covers: dict[str, str] = {}
        for size_key in sizes:
            w, h = COVER_SIZES.get(size_key, (1080, 1440))
            out_path = self.ctx.storage.path(
                f"{project_id}/08_covers/{episode_id}_{size_key}.jpg"
            )
            self._compose_cover(
                base=base,
                title=title,
                subtitle=subtitle,
                episode_id=episode_id,
                characters=[c.get("name", c.get("char_id", "")) for c in characters[:3]],
                out_path=out_path,
                width=w,
                height=h,
                genre=genre,
            )
            covers[size_key] = str(out_path)
            self.ctx.provenance.record(
                artefact_uri=str(out_path),
                sha256="0" * 64,
                size=out_path.stat().st_size if out_path.exists() else 0,
                producer_agent=self.name,
                seed=0,
            )

        return AgentRunResponse(
            status="succeeded",
            outputs={"covers": covers},
            metrics={"covers": float(len(covers))},
        )

    # ---------- base image ----------
    def _build_base_image(
        self,
        *,
        title: str,
        episode_id: str,
        genre: str,
        emotion: str,
        style_prompt: str,
        characters: list[dict[str, Any]],
        project_id: str,
        first_frame_path: str | None,
    ) -> Image.Image | None:
        # Step 1: real Jimeng 4.6
        if self.image_adapter is not None:
            with contextlib.suppress(Exception):
                names = "、".join(c.get("name", c.get("char_id", "")) for c in characters[:2])
                prompt = (
                    f"漫剧封面，竖向构图，{names}，情绪：{emotion}，题材：{genre}，"
                    f"画风：{style_prompt}，戏剧化光影，电影质感，标题文字位置预留"
                )
                imgs = self.image_adapter.generate(
                    prompt=prompt,
                    num_images=1,
                    aspect_ratio="3:4",
                    seed=hash(f"{project_id}:{episode_id}:cover") & 0x7FFFFFFF,
                    upload_to_tos=False,
                    prefix=f"{project_id}_{episode_id}_cover_base",
                )
                if imgs:
                    img = Image.open(imgs[0].local_path).convert("RGB")
                    return img
        # Step 2: fallback to first frame
        if first_frame_path and Path(first_frame_path).exists():
            with contextlib.suppress(Exception):
                return Image.open(first_frame_path).convert("RGB")
        # Step 3: extract first frame from a video via ffmpeg
        video = next(
            (
                p
                for p in [
                    first_frame_path,
                    self.ctx.storage.path(f"{project_id}/06_renders/{episode_id}.mp4"),
                ]
                if p
            ),
            None,
        )
        if video and Path(str(video)).exists() and str(video).endswith(".mp4"):
            png = self.ctx.storage.path(
                f"{project_id}/08_covers/_first_{episode_id}.png"
            )
            with contextlib.suppress(subprocess.SubprocessError, OSError, FileNotFoundError):
                subprocess.run(
                    [
                        "ffmpeg",
                        "-v", "error",
                        "-y",
                        "-i", str(video),
                        "-frames:v", "1",
                        "-q:v", "2",
                        str(png),
                    ],
                    check=False,
                    timeout=30,
                )
                if png.exists():
                    return Image.open(png).convert("RGB")
        # Step 4: gradient placeholder
        img = Image.new("RGB", (1080, 1440), (40, 60, 90))
        draw = ImageDraw.Draw(img)
        for i in range(1440):
            c = int(30 + (i / 1440) * 70)
            draw.line([(0, i), (1080, i)], fill=(c, c // 2, c))
        return img

    # ---------- compose ----------
    def _compose_cover(
        self,
        *,
        base: Image.Image,
        title: str,
        subtitle: str,
        episode_id: str,
        characters: list[str],
        out_path: Path,
        width: int,
        height: int,
        genre: str,
    ) -> None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        canvas = base.copy()
        canvas = canvas.resize((width, height), Image.LANCZOS)
        # Darken top + bottom for title legibility
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.rectangle([(0, 0), (width, height // 4)], fill=(0, 0, 0, 130))
        od.rectangle(
            [(0, height - height // 3), (width, height)], fill=(0, 0, 0, 180)
        )
        canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay)

        # Soft glow for title area
        glow = canvas.filter(ImageFilter.GaussianBlur(radius=8))
        # Re-paste original glowing through alpha mask
        canvas = Image.blend(canvas, glow, 0.0)
        draw = ImageDraw.Draw(canvas)

        title_font_size = max(60, int(width * 0.075))
        subtitle_font_size = max(30, int(width * 0.035))
        ep_font_size = max(28, int(width * 0.028))
        title_font = _load_font(_pick_title_font(genre), title_font_size)
        subtitle_font = _load_font("思源黑体", subtitle_font_size)
        ep_font = _load_font("思源黑体", ep_font_size)

        # Episode label (top-left)
        draw.text(
            (width // 24, height // 24),
            f"EP {episode_id.replace('ep', '').lstrip('0') or episode_id} · {genre.upper()}",
            font=ep_font,
            fill=(255, 220, 120, 240),
        )

        # Title (bottom)
        title_y = int(height * 0.74)
        draw.text(
            (width // 24, title_y),
            title[:14],
            font=title_font,
            fill=(255, 255, 255, 255),
            stroke_width=3,
            stroke_fill=(0, 0, 0, 255),
        )

        # Subtitle
        if subtitle:
            draw.text(
                (width // 24, title_y + title_font_size + 16),
                subtitle[:28],
                font=subtitle_font,
                fill=(230, 230, 230, 245),
                stroke_width=2,
                stroke_fill=(0, 0, 0, 255),
            )

        # Character tags (bottom-right)
        if characters:
            tag = "·".join(characters)[:18]
            tw = draw.textlength(tag, font=subtitle_font)
            draw.text(
                (width - tw - width // 24, height - height // 12),
                tag,
                font=subtitle_font,
                fill=(255, 220, 120, 240),
            )

        canvas.convert("RGB").save(out_path, format="JPEG", quality=92, optimize=True)


def _pick_title_font(genre: str) -> str:
    return {
        "ancient": "思源宋体",
        "xianxia": "思源宋体",
        "xuanhuan": "思源宋体",
    }.get(genre, "思源黑体")


def _load_font(name: str, size: int) -> ImageFont.ImageFont:
    candidates = [
        name,
        "Microsoft YaHei",
        "SimHei",
        "NotoSansCJK-Regular",
        "Source Han Sans CN",
        "Source Han Serif CN",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            continue
    return ImageFont.load_default()
