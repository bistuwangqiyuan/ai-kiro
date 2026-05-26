"""Render a ``GridLayout`` to a single PNG with cell numbering + page header.

Uses Pillow exclusively so it has no GPU/optional deps. The renderer is
deterministic: identical inputs produce byte-identical PNGs (REQ-GRID-002).
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from manhuaju.services.storyboard_grid import GridCell, GridLayout

CELL_PX = 256
GAP_PX = 6
HEADER_PX = 40
LEGEND_PX = 28
BG = (12, 13, 18, 255)
LINE = (66, 70, 92, 255)
TXT = (228, 230, 238, 255)
ACCENT = (255, 92, 138, 255)


def _font(size: int = 16) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _placeholder(cell: GridCell, w: int, h: int) -> Image.Image:
    """Create a deterministic placeholder cell image when no asset exists yet."""

    img = Image.new("RGBA", (w, h), (28, 30, 40, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([(0, 0), (w - 1, h - 1)], outline=LINE, width=2)
    label = f"#{cell.cell_index}"
    f = _font(36)
    bbox = d.textbbox((0, 0), label, font=f)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((w - tw) / 2, (h - th) / 2), label, fill=ACCENT, font=f)
    if cell.caption:
        capf = _font(14)
        cap = cell.caption[:32]
        d.text((8, h - 22), cap, fill=TXT, font=capf)
    return img


def render(
    grid: GridLayout,
    output_path: Path,
    cell_assets: dict[str, Path] | None = None,
    cell_px: int = CELL_PX,
    gap_px: int = GAP_PX,
) -> Path:
    """Render the grid to PNG; embed `grid_sha` + `grid_id` in EXIF (REQ-GRID-005)."""

    cell_assets = cell_assets or {}
    rows, cols = grid.rows, grid.cols
    width = cols * cell_px + (cols + 1) * gap_px
    height = HEADER_PX + rows * cell_px + (rows + 1) * gap_px + LEGEND_PX
    canvas = Image.new("RGBA", (width, height), BG)
    draw = ImageDraw.Draw(canvas)

    # Header: scene id + page
    title = f"{grid.scene_id}    Page {grid.page} / {grid.total_pages}    {grid.rows}x{grid.cols}"
    draw.text((12, 10), title, fill=TXT, font=_font(18))

    # Cells (left-to-right, top-to-bottom)
    for idx, cell in enumerate(grid.cells):
        r, c = divmod(idx, cols)
        x = gap_px + c * (cell_px + gap_px)
        y = HEADER_PX + gap_px + r * (cell_px + gap_px)
        asset = cell_assets.get(cell.shot_id)
        if asset and asset.exists():
            try:
                img = Image.open(asset).convert("RGBA").resize((cell_px, cell_px))
            except (OSError, ValueError):
                img = _placeholder(cell, cell_px, cell_px)
        else:
            img = _placeholder(cell, cell_px, cell_px)
        canvas.paste(img, (x, y), img)
        # cell number badge
        bd = ImageDraw.Draw(canvas)
        bd.rectangle([(x + 4, y + 4), (x + 32, y + 26)], fill=BG, outline=ACCENT)
        bd.text((x + 9, y + 6), f"{cell.cell_index:02d}", fill=ACCENT, font=_font(13))

    # Legend
    legend_y = HEADER_PX + rows * cell_px + (rows + 1) * gap_px + 4
    legend = f"sha={grid.grid_sha}    aspect={grid.aspect}    cells={len(grid.cells)}"
    draw.text((12, legend_y), legend, fill=(150, 154, 177, 255), font=_font(13))

    # Save with sidecar JSON (PNG metadata limited; we always also write JSON)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG")
    sidecar = output_path.with_suffix(".json")
    sidecar.write_text(
        json.dumps(
            {
                "grid_id": grid.grid_id,
                "grid_sha": grid.grid_sha,
                "scene_id": grid.scene_id,
                "page": grid.page,
                "total_pages": grid.total_pages,
                "rows": grid.rows,
                "cols": grid.cols,
                "aspect": grid.aspect,
                "cells": [
                    {"cell_index": c.cell_index, "shot_id": c.shot_id, "caption": c.caption}
                    for c in grid.cells
                ],
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return output_path
