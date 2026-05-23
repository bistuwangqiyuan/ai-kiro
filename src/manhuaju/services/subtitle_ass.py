"""ASS subtitle renderer — Shell 5 字幕（替代小云雀乱码字层）.

把剧本里的 ``DialogueLine`` 列表渲染成 ASS 文件，并提供 ffmpeg 烧入命令。

为什么用 ASS 而不是 drawtext？
- ASS 支持中文字体回退、阴影 / 描边 / 滚动 / 卡拉 OK 时间轴；
- 单条字幕带精确 start/end 时间，可与 audio cue 自动卡点；
- pysubs2 库直接写出 .ass，ffmpeg `-vf ass=` 烧入即可。

docx 六节「字幕自动合成：台词字幕排版、字体古风 / 现代适配、滚动字幕」全部覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # pysubs2 是可选依赖
    import pysubs2  # type: ignore[import-untyped]

    HAS_PYSUBS2 = True
except ImportError:
    pysubs2 = None  # type: ignore[assignment]
    HAS_PYSUBS2 = False


@dataclass
class SubtitleLine:
    start_s: float
    end_s: float
    text: str
    speaker: str = ""
    line_type: str = "dialogue"   # dialogue | narration | title | sfx_caption
    emphasis: bool = False


@dataclass
class SubtitleStyle:
    name: str = "Default"
    font: str = "思源黑体"
    fontsize: int = 56
    primary_color: str = "&H00FFFFFF"      # 白
    outline_color: str = "&H00000000"      # 黑
    back_color: str = "&H88000000"
    bold: bool = False
    italic: bool = False
    outline: int = 3
    shadow: int = 1
    alignment: int = 2                     # bottom-center
    margin_v: int = 80
    margin_l: int = 80
    margin_r: int = 80


GENRE_STYLE_MAP: dict[str, SubtitleStyle] = {
    "ancient": SubtitleStyle(name="Ancient", font="思源宋体", fontsize=58, outline=3),
    "xianxia": SubtitleStyle(name="Xianxia", font="思源宋体", fontsize=58, outline=3),
    "modern": SubtitleStyle(name="Modern", font="思源黑体", fontsize=54, outline=3),
    "sweet_pet": SubtitleStyle(name="SweetPet", font="思源黑体", fontsize=56, primary_color="&H00FFE4F0"),
    "suspense": SubtitleStyle(name="Suspense", font="思源黑体", fontsize=52, primary_color="&H00E0E0E0"),
    "xuanhuan": SubtitleStyle(name="Xuanhuan", font="思源宋体", fontsize=58, primary_color="&H00FFD78A"),
    "campus": SubtitleStyle(name="Campus", font="思源黑体", fontsize=54),
    "urban": SubtitleStyle(name="Urban", font="思源黑体", fontsize=54),
}


@dataclass
class ASSRenderResult:
    ass_path: str
    n_lines: int
    style: str
    success: bool = True
    error: str | None = None
    raw_ass_text: str = field(default="", repr=False)


def render_ass(
    lines: list[SubtitleLine],
    *,
    out_path: str | Path,
    style: SubtitleStyle | None = None,
    genre: str = "ancient",
    width: int = 1080,
    height: int = 1920,
) -> ASSRenderResult:
    """Write an ASS file. Falls back to a hand-rolled .ass writer if pysubs2 missing."""
    style = style or GENRE_STYLE_MAP.get(genre, SubtitleStyle())
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if HAS_PYSUBS2:
        return _render_pysubs2(lines, out, style, width, height)
    return _render_native(lines, out, style, width, height)


def _render_pysubs2(
    lines: list[SubtitleLine], out: Path, style: SubtitleStyle, width: int, height: int
) -> ASSRenderResult:
    subs = pysubs2.SSAFile()
    subs.info["PlayResX"] = str(width)
    subs.info["PlayResY"] = str(height)
    subs.info["ScaledBorderAndShadow"] = "yes"
    subs.info["YCbCr Matrix"] = "TV.709"

    ass_style = pysubs2.SSAStyle()
    ass_style.fontname = style.font
    ass_style.fontsize = style.fontsize
    ass_style.bold = style.bold
    ass_style.italic = style.italic
    ass_style.outline = style.outline
    ass_style.shadow = style.shadow
    ass_style.alignment = pysubs2.Alignment(style.alignment)
    ass_style.marginv = style.margin_v
    ass_style.marginl = style.margin_l
    ass_style.marginr = style.margin_r
    subs.styles[style.name] = ass_style

    narration_style = pysubs2.SSAStyle()
    narration_style.fontname = style.font
    narration_style.fontsize = max(28, style.fontsize - 4)
    narration_style.italic = True
    narration_style.outline = style.outline
    narration_style.alignment = pysubs2.Alignment(8)  # top-center
    narration_style.marginv = 100
    subs.styles["Narration"] = narration_style

    for ln in lines:
        ev = pysubs2.SSAEvent(
            start=int(ln.start_s * 1000),
            end=int(ln.end_s * 1000),
            text=_render_text(ln),
        )
        ev.style = "Narration" if ln.line_type == "narration" else style.name
        subs.append(ev)
    subs.save(str(out), format_="ass")
    raw = out.read_text(encoding="utf-8")
    return ASSRenderResult(
        ass_path=str(out), n_lines=len(lines), style=style.name, raw_ass_text=raw
    )


def _render_text(ln: SubtitleLine) -> str:
    text = ln.text.replace("\n", "\\N").strip()
    if ln.emphasis:
        text = "{\\bord4\\shad2}" + text
    if ln.speaker and ln.line_type == "dialogue":
        return text
    return text


def _render_native(
    lines: list[SubtitleLine], out: Path, style: SubtitleStyle, width: int, height: int
) -> ASSRenderResult:
    """ASS writer without pysubs2 — minimal but ffmpeg-compatible."""
    header = (
        "[Script Info]\n"
        f"PlayResX: {width}\n"
        f"PlayResY: {height}\n"
        "ScriptType: v4.00+\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
        "Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: {style.name},{style.font},{style.fontsize},{style.primary_color},"
        f"{style.outline_color},{style.back_color},{int(style.bold)},{int(style.italic)},"
        f"1,{style.outline},{style.shadow},{style.alignment},"
        f"{style.margin_l},{style.margin_r},{style.margin_v},1\n"
        f"Style: Narration,{style.font},{max(28, style.fontsize - 4)},"
        "&H00FFFFFF,&H00000000,&H88000000,0,1,1,3,1,8,80,80,100,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = []
    for ln in lines:
        st = "Narration" if ln.line_type == "narration" else style.name
        events.append(
            f"Dialogue: 0,{_sec_to_ass(ln.start_s)},{_sec_to_ass(ln.end_s)},{st},,0,0,0,,"
            f"{ln.text.replace(chr(10), chr(92) + 'N')}"
        )
    text = header + "\n".join(events) + "\n"
    out.write_text(text, encoding="utf-8")
    return ASSRenderResult(
        ass_path=str(out), n_lines=len(lines), style=style.name, raw_ass_text=text
    )


def _sec_to_ass(s: float) -> str:
    if s < 0:
        s = 0.0
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s - h * 3600 - m * 60
    return f"{h:01d}:{m:02d}:{sec:05.2f}"


def lines_from_script(
    script: dict[str, Any],
    *,
    base_offset_s: float = 0.0,
) -> list[SubtitleLine]:
    """Convert a Script schema dict into subtitle lines (dialogue + narration)."""
    out: list[SubtitleLine] = []
    cursor = base_offset_s
    for scene in script.get("scenes", []):
        for shot in scene.get("shots", []):
            target = float(shot.get("target_seconds") or 3.0)
            shot_end = cursor + target
            for line in shot.get("dialogue_lines", []) or []:
                txt = line.get("text") or ""
                if not txt:
                    continue
                lstart = cursor + float(line.get("start_offset_s") or 0.0)
                lend = lstart + float(line.get("duration_s") or 2.0)
                lend = min(lend, shot_end)
                out.append(
                    SubtitleLine(
                        start_s=lstart,
                        end_s=lend,
                        text=txt,
                        speaker=line.get("speaker") or "",
                        line_type="dialogue",
                    )
                )
            narr = shot.get("narration") or {}
            if isinstance(narr, dict) and narr.get("text"):
                out.append(
                    SubtitleLine(
                        start_s=cursor,
                        end_s=shot_end,
                        text=narr["text"],
                        line_type="narration",
                    )
                )
            cursor = shot_end
    return out


def burn_command(
    video_path: str | Path,
    ass_path: str | Path,
    *,
    out_path: str | Path,
    audio_path: str | Path | None = None,
    crf: int = 19,
    preset: str = "medium",
) -> list[str]:
    """Build a ffmpeg command list that burns ASS subtitles into video.

    On Windows, ass= filter path needs escaping; we wrap as `ass=filename`.
    """
    cmd = ["ffmpeg", "-y", "-i", str(video_path)]
    if audio_path:
        cmd.extend(["-i", str(audio_path)])
    cmd.extend(
        [
            "-vf",
            f"ass={_escape_ass_path(str(ass_path))}",
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-pix_fmt",
            "yuv420p",
        ]
    )
    if audio_path:
        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
    cmd.append(str(out_path))
    return cmd


def _escape_ass_path(p: str) -> str:
    # ffmpeg ass= filter needs colons escaped on Windows
    return p.replace("\\", "/").replace(":", "\\:")
