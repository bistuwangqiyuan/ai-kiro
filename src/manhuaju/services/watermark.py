"""Cover-image watermark + signature service (REQ-DIST-002 / -003).

Adds a deterministic watermark text + an alpha-compositing layer to a PIL
image. Position is one of {bottom_right, bottom_left, top_right, top_left}.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont

WatermarkPosition = Literal["bottom_right", "bottom_left", "top_right", "top_left"]


@dataclass(frozen=True)
class WatermarkResult:
    output_path: str
    text: str
    position: WatermarkPosition
    font_size: int
    opacity: float


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _coords(text_w: int, text_h: int, img_w: int, img_h: int, pad: int, pos: WatermarkPosition) -> tuple[int, int]:
    if pos == "bottom_right":
        return (img_w - text_w - pad, img_h - text_h - pad)
    if pos == "bottom_left":
        return (pad, img_h - text_h - pad)
    if pos == "top_right":
        return (img_w - text_w - pad, pad)
    return (pad, pad)


def apply_watermark(
    input_path: Path | str,
    output_path: Path | str,
    *,
    text: str = "© Manhuaju Autopilot",
    position: WatermarkPosition = "bottom_right",
    font_size: int = 24,
    opacity: float = 0.65,
) -> WatermarkResult:
    """REQ-DIST-002: stamp watermark with deterministic position + opacity."""

    if not (0.0 < opacity <= 1.0):
        raise ValueError("opacity must be in (0, 1]")
    img = Image.open(input_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = int(bbox[2] - bbox[0]), int(bbox[3] - bbox[1])
    x, y = _coords(text_w, text_h, img.size[0], img.size[1], pad=18, pos=position)
    alpha = int(255 * opacity)
    # Subtle dark backplate for readability
    draw.rectangle(
        [(x - 8, y - 4), (x + text_w + 8, y + text_h + 6)],
        fill=(0, 0, 0, int(alpha * 0.4)),
    )
    draw.text((x, y), text, fill=(255, 255, 255, alpha), font=font)
    out = Image.alpha_composite(img, overlay).convert("RGB")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out.save(output_path, format="PNG")
    return WatermarkResult(
        output_path=str(output_path),
        text=text,
        position=position,
        font_size=font_size,
        opacity=opacity,
    )
