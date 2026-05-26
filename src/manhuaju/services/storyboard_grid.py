"""Storyboard 9-25 cell grid layout (REQ-GRID-001..006).

Picks a grid size in {9, 12, 16, 20, 25} given shot count + aspect ratio,
paginates when shots exceed 25, and returns ``GridLayout`` instances ready
for rendering by ``grid_renderer``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal

AspectRatio = Literal["16:9", "9:16", "1:1", "4:5", "21:9"]


_GRID_SIZES_PORTRAIT = (9, 12, 16, 20, 25)
_GRID_SIZES_LANDSCAPE = (9, 12, 16, 20, 25)


@dataclass(frozen=True)
class GridCell:
    cell_index: int
    shot_id: str
    caption: str = ""


@dataclass(frozen=True)
class GridLayout:
    grid_id: str
    scene_id: str
    rows: int
    cols: int
    cells: tuple[GridCell, ...]
    page: int
    total_pages: int
    aspect: AspectRatio
    grid_sha: str = field(default="")

    @property
    def capacity(self) -> int:
        return self.rows * self.cols


def _pick_grid_dims(n_shots: int, aspect: AspectRatio) -> tuple[int, int]:
    """Choose (rows, cols) such that rows*cols >= n_shots and shape suits aspect.

    Strategy:
        * portrait (9:16, 4:5): cols ≤ rows (e.g. 4×3, 5×4)
        * landscape (16:9, 21:9): cols ≥ rows (e.g. 3×4, 4×5)
        * square (1:1): rows == cols (e.g. 3×3, 4×4)
    """

    capacity_options = (
        (3, 3, 9),
        (3, 4, 12),
        (4, 4, 16),
        (4, 5, 20),
        (5, 5, 25),
    )
    chosen = None
    for r, c, cap in capacity_options:
        if cap >= n_shots:
            chosen = (r, c, cap)
            break
    if chosen is None:
        chosen = (5, 5, 25)
    rows, cols, _cap = chosen
    if aspect in ("9:16", "4:5"):
        return max(rows, cols), min(rows, cols)
    if aspect in ("16:9", "21:9"):
        return min(rows, cols), max(rows, cols)
    return rows, cols


def layout(
    scene_id: str,
    shots: list[dict[str, str]],
    aspect: AspectRatio = "9:16",
) -> list[GridLayout]:
    """Build paginated GridLayouts for one scene.

    Each ``shots[i]`` must have at least ``shot_id`` (and optional ``caption``).
    Returns one or more ``GridLayout`` (paginated when shots > 25).
    """

    if not shots:
        raise ValueError("shots must not be empty")

    cells_per_page = 25
    pages = []
    total_pages = max(1, (len(shots) + cells_per_page - 1) // cells_per_page)
    for page_idx, start in enumerate(range(0, len(shots), cells_per_page), start=1):
        page_shots = shots[start : start + cells_per_page]
        rows, cols = _pick_grid_dims(len(page_shots), aspect)
        cells = tuple(
            GridCell(
                cell_index=i + 1,
                shot_id=s["shot_id"],
                caption=s.get("caption", ""),
            )
            for i, s in enumerate(page_shots)
        )
        sha = hashlib.sha256(
            f"{scene_id}|{page_idx}|{rows}x{cols}|{','.join(c.shot_id for c in cells)}".encode()
        ).hexdigest()[:16]
        pages.append(
            GridLayout(
                grid_id=f"{scene_id}-grid-p{page_idx}",
                scene_id=scene_id,
                rows=rows,
                cols=cols,
                cells=cells,
                page=page_idx,
                total_pages=total_pages,
                aspect=aspect,
                grid_sha=sha,
            )
        )
    return pages


def regenerate_cell(grid: GridLayout, cell_index: int, new_shot_id: str, new_caption: str = "") -> GridLayout:
    """REQ-GRID-004: replace a single cell, recompute SHA, leave others untouched."""

    if cell_index < 1 or cell_index > grid.capacity:
        raise ValueError(f"cell_index {cell_index} out of range 1..{grid.capacity}")
    new_cells = tuple(
        GridCell(
            cell_index=c.cell_index,
            shot_id=new_shot_id if c.cell_index == cell_index else c.shot_id,
            caption=new_caption if c.cell_index == cell_index else c.caption,
        )
        for c in grid.cells
    )
    sha = hashlib.sha256(
        f"{grid.scene_id}|{grid.page}|{grid.rows}x{grid.cols}|{','.join(c.shot_id for c in new_cells)}".encode()
    ).hexdigest()[:16]
    return GridLayout(
        grid_id=grid.grid_id,
        scene_id=grid.scene_id,
        rows=grid.rows,
        cols=grid.cols,
        cells=new_cells,
        page=grid.page,
        total_pages=grid.total_pages,
        aspect=grid.aspect,
        grid_sha=sha,
    )
